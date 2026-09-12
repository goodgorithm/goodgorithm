import type { FastifyInstance } from "fastify";

import { checkDatabaseConnection } from "../db";

// Same deploy-skew-visibility reason as api/'s health route (CLAUDE.md's
// Versioning & migration section) -- railway-deploy.sh sets this from
// GitHub Actions' $GITHUB_SHA before each deploy.
const VERSION = process.env.GIT_COMMIT_SHA ?? process.env.RAILWAY_GIT_COMMIT_SHA ?? "unknown";

export async function healthRoute(app: FastifyInstance): Promise<void> {
  app.get("/health", async (_request, reply) => {
    const db = await checkDatabaseConnection();
    const body = {
      status: db.reachable ? "ok" : "error",
      version: VERSION,
      timestamp: new Date().toISOString(),
      database: db.reachable
        ? { reachable: true, latency_ms: db.latencyMs }
        : { reachable: false, latency_ms: db.latencyMs, error: db.error },
    };
    if (!db.reachable) {
      return reply.code(503).send(body);
    }
    return body;
  });
}
