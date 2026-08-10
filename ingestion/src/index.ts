import "dotenv/config";
import { startBlueskyIngestion } from "./bluesky";
import { startBlueskyLabelIngestion } from "./blueskyLabels";
import { startMastodonIngestion } from "./mastodon";
import { close } from "./db";
import { startHeartbeat } from "./heartbeat";

if (!process.env.DATABASE_URL) {
  console.error("DATABASE_URL is required");
  process.exit(1);
}

console.log("[ingestion] starting");
startBlueskyIngestion();
startBlueskyLabelIngestion();
startMastodonIngestion();
startHeartbeat(process.env.HEARTBEAT_URL_INGESTION);

process.on("SIGTERM", async () => {
  console.log("[ingestion] shutting down");
  await close();
  process.exit(0);
});
