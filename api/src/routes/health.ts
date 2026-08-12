import type { FastifyInstance } from "fastify";

import { checkDatabaseConnection } from "../db";

// Railway's auto-provided commit SHA for the running deployment - "unknown"
// outside Railway (e.g. local dev, where this env var is unset). See
// CLAUDE.md's Versioning & migration section: makes the real, confirmed
// deploy-skew window between services (railway-deploy.sh deploys
// ingestion/api/processing sequentially, tolerating partial failure)
// observable instead of invisible.
const VERSION = process.env.RAILWAY_GIT_COMMIT_SHA ?? "unknown";

export async function healthRoute(app: FastifyInstance): Promise<void> {
  app.get("/health", async (_request, reply) => {
    const dbOk = await checkDatabaseConnection();
    if (!dbOk) {
      return reply.code(503).send({ status: "error", database: "unreachable", version: VERSION });
    }
    return { status: "ok", version: VERSION };
  });
}
