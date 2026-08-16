import "dotenv/config";

import { buildApp } from "./app";
import { close } from "./db";

if (!process.env.DATABASE_URL) {
  console.error("DATABASE_URL is required");
  process.exit(1);
}

async function main(): Promise<void> {
  const app = await buildApp();

  process.on("SIGTERM", async () => {
    app.log.info("shutting down");
    await app.close();
    await close();
    process.exit(0);
  });

  const port = Number(process.env.PORT ?? 3000);
  // 0.0.0.0, not configurable - binding to all interfaces is required for
  // Railway/container networking to reach the process at all, not a
  // per-environment preference.
  await app.listen({ host: "0.0.0.0", port });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
