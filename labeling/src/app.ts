import Fastify, { type FastifyInstance } from "fastify";

import { apiRoutes } from "./routes/api";
import { healthRoute } from "./routes/health";
import { uiRoute } from "./routes/ui";

export async function buildApp(): Promise<FastifyInstance> {
  const app = Fastify({ logger: true });

  // /health stays unauthenticated and unversioned -- an infra-level check
  // (Railway's healthcheckPath), same reasoning as api/'s health route.
  await app.register(healthRoute);

  await app.register(apiRoutes);
  await app.register(uiRoute);

  return app;
}
