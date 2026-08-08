import "dotenv/config";
import cors from "@fastify/cors";
import Fastify from "fastify";

import { close } from "./db";
import { feedRoute } from "./routes/feed";
import { healthRoute } from "./routes/health";

if (!process.env.DATABASE_URL) {
  console.error("DATABASE_URL is required");
  process.exit(1);
}

const app = Fastify({ logger: true });

async function main(): Promise<void> {
  // public, read-only, unauthenticated API — no credentials/cookies involved
  await app.register(cors, { origin: true });
  await app.register(healthRoute);
  await app.register(feedRoute);

  const port = Number(process.env.PORT ?? 3000);
  await app.listen({ host: "0.0.0.0", port });
}

main().catch((err) => {
  app.log.error(err);
  process.exit(1);
});

process.on("SIGTERM", async () => {
  app.log.info("shutting down");
  await app.close();
  await close();
  process.exit(0);
});
