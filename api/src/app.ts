import cors from "@fastify/cors";
import rateLimit from "@fastify/rate-limit";
import Fastify, { type FastifyInstance } from "fastify";

import { feedRoute } from "./routes/feed";
import { healthRoute } from "./routes/health";

export async function buildApp(): Promise<FastifyInstance> {
  // trustProxy so rate limiting keys on the real client IP (from
  // X-Forwarded-For) rather than Railway's edge proxy for every request
  const app = Fastify({ logger: true, trustProxy: true });

  // public, read-only, unauthenticated API — no credentials/cookies involved
  await app.register(cors, { origin: true });

  // No accounts, so IP is the only identity we have. Limit is sized to
  // absorb normal feed-scrolling traffic while blocking spam/scraping bursts.
  await app.register(rateLimit, { max: 100, timeWindow: "1 minute" });

  await app.register(healthRoute);
  await app.register(feedRoute);

  return app;
}
