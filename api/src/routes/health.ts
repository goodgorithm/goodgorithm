import type { FastifyInstance } from "fastify";

import { checkDatabaseConnection } from "../db";

// The running deployment's commit SHA, for the same deploy-skew-visibility
// reason described in CLAUDE.md's Versioning & migration section
// (railway-deploy.sh deploys ingestion/api/processing sequentially,
// tolerating partial failure). Railway only auto-populates
// RAILWAY_GIT_COMMIT_SHA for deploys it triggers itself via its native
// GitHub integration -- this repo deploys via `railway up` from GitHub
// Actions instead (see railway-deploy.sh's own comments on why), which
// doesn't count as a "GitHub trigger" even though the service's source is
// configured with a repo/branch. Confirmed via Railway's docs and a live
// `railway variable list` check, 2026-08-13: RAILWAY_GIT_COMMIT_SHA was
// absent from both staging and production, hence /health always reporting
// "unknown". GIT_COMMIT_SHA is set explicitly by railway-deploy.sh from
// GitHub Actions' $GITHUB_SHA before each deploy; RAILWAY_GIT_COMMIT_SHA is
// kept as a fallback in case the deploy mechanism ever reverts to Railway's
// native GitHub-triggered builds. "unknown" outside both (e.g. local dev).
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
