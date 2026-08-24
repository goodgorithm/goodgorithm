import { createServer } from "http";
import { getConnectionState as getBlueskyState } from "./bluesky";
import { getConnectionState as getBlueskyLabelsState } from "./blueskyLabels";
import { getInstanceStatus } from "./mastodon";
import { pendingExclusionCount } from "./pendingExclusions";

// Auditable first-look status, not a log replacement -- narrows down where
// to look next, doesn't replace digging through logs for the actual
// detail. No existing HTTP server in ingestion/ before this (it's a pure
// WebSocket/polling process), so this uses Node's built-in http module
// rather than adding a framework dependency for one static route -- same
// reasoning as processing/'s new status server using Python's built-in
// http.server instead of adding Flask/FastAPI.

interface PublicConfig {
  [key: string]: unknown;
}

function buildStatus(publicConfig: PublicConfig) {
  return {
    bluesky: getBlueskyState(),
    blueskyLabels: getBlueskyLabelsState(),
    mastodon: getInstanceStatus(),
    pendingExclusionCount: pendingExclusionCount(),
    config: publicConfig,
  };
}

export function startStatusServer(port: number, publicConfig: PublicConfig): void {
  const server = createServer((req, res) => {
    if (req.url !== "/health") {
      res.writeHead(404).end();
      return;
    }
    const body = JSON.stringify(buildStatus(publicConfig));
    res.writeHead(200, { "Content-Type": "application/json" }).end(body);
  });
  server.listen(port, () => {
    console.log(`[ingestion] status server listening on :${port}/health`);
  });
}
