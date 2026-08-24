import "dotenv/config";
import { startBlueskyIngestion } from "./bluesky";
import { startBlueskyLabelIngestion } from "./blueskyLabels";
import { startMastodonIngestion } from "./mastodon";
import { close } from "./db";
import { startHeartbeat } from "./heartbeat";
import { startStatusServer } from "./statusServer";

// Backstop for any async call site that doesn't already have a local
// try/catch -- today's coverage is complete by discipline (every risky
// call site in bluesky.ts/blueskyLabels.ts/mastodon.ts already catches
// locally), not by a safety net. This exists so a future gap crashes
// loudly and gets logged clearly, rather than however Node's own default
// unhandled-rejection behavior happens to render it. Matches processing/'s
// "an uncaught failure should crash loudly, not be silently swallowed"
// philosophy -- this is not a way to keep running past an error nobody
// planned for.
process.on("unhandledRejection", (reason) => {
  console.error("[ingestion] unhandled rejection:", reason);
  process.exit(1);
});
process.on("uncaughtException", (err) => {
  console.error("[ingestion] uncaught exception:", err);
  process.exit(1);
});

if (!process.env.DATABASE_URL) {
  console.error("DATABASE_URL is required");
  process.exit(1);
}

console.log("[ingestion] starting");
startBlueskyIngestion();
startBlueskyLabelIngestion();
startMastodonIngestion();
startHeartbeat(process.env.HEARTBEAT_URL_INGESTION);

// Public, safe-to-expose config only -- never DATABASE_URL or
// HEARTBEAT_URL_INGESTION (an unguessable bearer-token-style URL; exposing
// it would let anyone spoof this service's own dead-man's-switch ping).
startStatusServer(Number(process.env.PORT ?? 8080), {
  blueskySampleRate: process.env.BLUESKY_SAMPLE_RATE ?? "1.0",
  blueskyReconnectBaseMs: process.env.BLUESKY_RECONNECT_BASE_MS ?? "5000",
  blueskyReconnectMaxMs: process.env.BLUESKY_RECONNECT_MAX_MS ?? "60000",
  disableLabelFilter: Boolean(process.env.DISABLE_LABEL_FILTER),
  mastodonPollIntervalMs: process.env.MASTODON_POLL_INTERVAL_MS ?? "30000",
  mastodonRequestTimeoutMs: process.env.MASTODON_REQUEST_TIMEOUT_MS ?? "10000",
  heartbeatIntervalMs: process.env.HEARTBEAT_INTERVAL_MS ?? "300000",
});

process.on("SIGTERM", async () => {
  console.log("[ingestion] shutting down");
  await close();
  process.exit(0);
});
