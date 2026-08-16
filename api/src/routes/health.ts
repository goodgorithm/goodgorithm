import type { FastifyInstance } from "fastify";

import { checkDatabaseConnection } from "../db";

// The running deployment's commit SHA, for the same deploy-skew-visibility
// reason described in CLAUDE.md's Versioning & migration section.
// GIT_COMMIT_SHA is set explicitly by railway-deploy.sh from GitHub
// Actions' $GITHUB_SHA before each deploy; RAILWAY_GIT_COMMIT_SHA is a
// fallback for Railway's own native-GitHub-trigger deploys, which this
// repo doesn't currently use. "unknown" outside both (e.g. local dev). See
// the wiki's API Internals page for why both env vars exist.
const VERSION = process.env.GIT_COMMIT_SHA ?? process.env.RAILWAY_GIT_COMMIT_SHA ?? "unknown";

export async function healthRoute(app: FastifyInstance): Promise<void> {
  app.get("/health", async (_request, reply) => {
    const dbOk = await checkDatabaseConnection();
    if (!dbOk) {
      return reply.code(503).send({ status: "error", database: "unreachable", version: VERSION });
    }
    return { status: "ok", version: VERSION };
  });
}
