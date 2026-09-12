import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";

import * as db from "../db";
import type { NewPost } from "../db";

// The whole access model for now, deliberately: no accounts, a single shared
// secret gates every route in this file. Room to grow into real per-person
// auth later without a schema change -- see labeling.labels' `reviewer`
// column. health stays separate, registered without this hook (app.ts).
// Read per-request rather than cached at module load, so it reflects
// whatever's actually configured right now rather than whatever was set at
// process start.
function requireAccessToken(request: FastifyRequest, reply: FastifyReply, done: (err?: Error) => void): void {
  const accessToken = process.env.LABELING_ACCESS_TOKEN;
  if (!accessToken) {
    // Fails closed, not open -- an unset token must never mean "no auth
    // required." Misconfiguration should be loud (500s on every request,
    // visible immediately), not a silent security hole.
    reply.code(500).send({ error: "LABELING_ACCESS_TOKEN is not configured" });
    return;
  }
  if (request.headers["x-access-token"] !== accessToken) {
    reply.code(401).send({ error: "unauthorized" });
    return;
  }
  done();
}

function isFilter(value: unknown): value is "unreviewed" | "flagged" | "all" {
  return value === "unreviewed" || value === "flagged" || value === "all";
}

function csvField(value: string): string {
  if (/[",\n]/.test(value)) return `"${value.replace(/"/g, '""')}"`;
  return value;
}

export async function apiRoutes(app: FastifyInstance): Promise<void> {
  app.addHook("preHandler", requireAccessToken);

  app.get("/api/studies", async () => {
    return { studies: await db.listStudies() };
  });

  app.get<{ Params: { slug: string }; Querystring: { filter?: string } }>(
    "/api/studies/:slug/posts",
    async (request, reply) => {
      const study = await db.getStudyBySlug(request.params.slug);
      if (!study) return reply.code(404).send({ error: "study not found" });

      const filter = isFilter(request.query.filter) ? request.query.filter : "unreviewed";
      const posts = await db.listPosts(study.id, filter);
      return { study, posts };
    },
  );

  app.post<{ Params: { slug: string }; Body: { posts: NewPost[] } }>(
    "/api/studies/:slug/posts",
    async (request, reply) => {
      const study = await db.getStudyBySlug(request.params.slug);
      if (!study) return reply.code(404).send({ error: "study not found" });

      const inserted = await db.insertPosts(study.id, request.body.posts ?? []);
      return { inserted };
    },
  );

  app.post<{ Params: { slug: string; id: string }; Body: { category: string; taxonomy_flag?: boolean; notes?: string } }>(
    "/api/studies/:slug/posts/:id/label",
    async (request, reply) => {
      const study = await db.getStudyBySlug(request.params.slug);
      if (!study) return reply.code(404).send({ error: "study not found" });

      const label = await db.submitLabel(request.params.id, {
        category: request.body.category,
        taxonomy_flag: request.body.taxonomy_flag ?? false,
        notes: request.body.notes ?? "",
      });
      return { label };
    },
  );

  app.get<{ Params: { slug: string } }>("/api/studies/:slug/export", async (request, reply) => {
    const study = await db.getStudyBySlug(request.params.slug);
    if (!study) return reply.code(404).send({ error: "study not found" });

    const rows = await db.exportLabelled(study.id);
    const header = "id,source,batch,category,taxonomy_flag,notes,labelled_at,text";
    const lines = rows.map((r) =>
      [
        r.id,
        r.source ?? "",
        r.batch ?? "",
        r.category,
        String(r.taxonomy_flag),
        csvField(r.notes),
        r.labelled_at.toISOString(),
        csvField(r.text),
      ].join(","),
    );
    reply.header("Content-Type", "text/csv");
    reply.header("Content-Disposition", `attachment; filename="${study.slug}.csv"`);
    return [header, ...lines].join("\n");
  });
}
