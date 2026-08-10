import type { FastifyInstance } from "fastify";

import { checkDatabaseConnection } from "../db";

export async function healthRoute(app: FastifyInstance): Promise<void> {
  app.get("/health", async (_request, reply) => {
    const dbOk = await checkDatabaseConnection();
    if (!dbOk) {
      return reply.code(503).send({ status: "error", database: "unreachable" });
    }
    return { status: "ok" };
  });
}
