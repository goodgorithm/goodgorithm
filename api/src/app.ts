import cors from "@fastify/cors";
import rateLimit from "@fastify/rate-limit";
import Fastify, { type FastifyInstance } from "fastify";

import { feedRoute } from "./routes/feed";
import { healthRoute } from "./routes/health";

// No accounts, so IP is the only identity available - sized to absorb
// normal feed-scrolling traffic while blocking spam/scraping bursts. See
// the wiki's Configuration page.
export const RATE_LIMIT_MAX = Number(process.env.RATE_LIMIT_MAX ?? 100);
export const RATE_LIMIT_TIME_WINDOW = process.env.RATE_LIMIT_TIME_WINDOW ?? "1 minute";

export async function buildApp(): Promise<FastifyInstance> {
  // trustProxy so rate limiting keys on the real client IP (from
  // X-Forwarded-For) rather than Railway's edge proxy for every request
  const app = Fastify({ logger: true, trustProxy: true });

  // public, read-only, unauthenticated API — no credentials/cookies involved
  await app.register(cors, { origin: true });

  await app.register(rateLimit, { max: RATE_LIMIT_MAX, timeWindow: RATE_LIMIT_TIME_WINDOW });

  // /health stays unversioned - it's an infra-level check (Railway's
  // healthcheckPath, Better Stack's external monitor), not part of the
  // data contract this versioning is actually protecting.
  await app.register(healthRoute);

  await app.register(feedRoute, { prefix: "/v1" });

  return app;
}
