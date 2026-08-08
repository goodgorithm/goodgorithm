import "dotenv/config";
import { startBlueskyIngestion } from "./bluesky";
import { startMastodonIngestion } from "./mastodon";
import { close } from "./db";

if (!process.env.DATABASE_URL) {
  console.error("DATABASE_URL is required");
  process.exit(1);
}

console.log("[ingestion] starting");
startBlueskyIngestion();
startMastodonIngestion();

process.on("SIGTERM", async () => {
  console.log("[ingestion] shutting down");
  await close();
  process.exit(0);
});
