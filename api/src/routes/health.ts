import type { FastifyInstance } from "fastify";

import { checkDatabaseConnection } from "../db";
import { FEED_LIMIT_DEFAULT, FEED_LIMIT_MAX } from "./feed";

// The running deployment's commit SHA, for the same deploy-skew-visibility
// reason described in CLAUDE.md's Versioning & migration section.
// GIT_COMMIT_SHA is set explicitly by railway-deploy.sh from GitHub
// Actions' $GITHUB_SHA before each deploy; RAILWAY_GIT_COMMIT_SHA is a
// fallback for Railway's own native-GitHub-trigger deploys, which this
// repo doesn't currently use. "unknown" outside both (e.g. local dev). See
// the wiki's API Internals page for why both env vars exist.
const VERSION = process.env.GIT_COMMIT_SHA ?? process.env.RAILWAY_GIT_COMMIT_SHA ?? "unknown";

// Public, safe-to-expose config only -- never DATABASE_URL. An auditable
// first-look, not a log replacement: narrows down where to look next,
// doesn't replace digging through logs for the actual detail. See
// CLAUDE.md's Service resilience section.
const DB_POOL_MAX_SIZE = Number(process.env.DB_POOL_MAX_SIZE ?? 5);
const HEALTH_CHECK_TIMEOUT_MS = Number(process.env.HEALTH_CHECK_TIMEOUT_MS ?? 3000);
const FEED_QUERY_TIMEOUT_MS = Number(process.env.FEED_QUERY_TIMEOUT_MS ?? 10000);
// Re-derived from the same env vars app.ts's own RATE_LIMIT_MAX/TIME_WINDOW
// read, rather than importing them from app.ts -- app.ts imports
// healthRoute from this file, so importing back would be circular.
// Matches this file's existing per-file env-var convention anyway (no
// shared config module in api/src/).
const RATE_LIMIT_MAX = Number(process.env.RATE_LIMIT_MAX ?? 100);
const RATE_LIMIT_TIME_WINDOW = process.env.RATE_LIMIT_TIME_WINDOW ?? "1 minute";

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
      config: {
        rate_limit_max: RATE_LIMIT_MAX,
        rate_limit_time_window: RATE_LIMIT_TIME_WINDOW,
        feed_limit_max: FEED_LIMIT_MAX,
        feed_limit_default: FEED_LIMIT_DEFAULT,
        db_pool_max_size: DB_POOL_MAX_SIZE,
        health_check_timeout_ms: HEALTH_CHECK_TIMEOUT_MS,
        feed_query_timeout_ms: FEED_QUERY_TIMEOUT_MS,
      },
    };
    if (!db.reachable) {
      return reply.code(503).send(body);
    }
    return body;
  });
}
