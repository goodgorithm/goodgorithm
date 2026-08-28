import { createServer } from "http";
import { getConnectionState as getBlueskyState } from "./bluesky";
import { getConnectionState as getBlueskyLabelsState } from "./blueskyLabels";
import { getInstanceStatus, type InstanceStatus } from "./mastodon";
import { pendingExclusionCount } from "./pendingExclusions";

// Auditable first-look status, not a log replacement -- narrows down where
// to look next, doesn't replace digging through logs for the actual
// detail. ingestion/ is otherwise a pure WebSocket/polling process, with
// no other inbound HTTP surface -- this uses Node's built-in http module
// rather than adding a framework dependency for one static route, same
// reasoning as processing/'s status server using Python's built-in
// http.server instead of adding Flask/FastAPI.

interface PublicConfig {
  [key: string]: unknown;
}

interface ConnectionState {
  connected: boolean;
}

// A pure function of the three connection-state shapes, so it's directly
// unit-testable with fake state -- no live connections needed. "degraded"
// here means "currently disconnected/failing", not "has ever failed" --
// this mirrors processing/'s status server's own "not degraded since this
// cycle" semantics, not a permanent black mark.
export function computeStatus(
  bluesky: ConnectionState,
  blueskyLabels: ConnectionState & { disabled: boolean },
  mastodon: Record<string, InstanceStatus>,
): "ok" | "degraded" {
  if (!bluesky.connected) return "degraded";
  if (!blueskyLabels.disabled && !blueskyLabels.connected) return "degraded";
  for (const status of Object.values(mastodon)) {
    // A poll that's never succeeded once isn't necessarily degraded on its
    // own (it may just not have run yet) -- only a poll whose most recent
    // attempt was an error, i.e. it previously worked and then started
    // failing, or every attempt so far has failed.
    if (status.lastErrorAt && (!status.lastSuccessAt || status.lastErrorAt > status.lastSuccessAt)) {
      return "degraded";
    }
  }
  return "ok";
}

// 503 when degraded, 200 otherwise -- lets /health/strict double as a plain
// up/down check for an external monitor. Kept off /health itself, which must
// stay 200 for Railway's deploy-time healthcheck (a degraded ingestion
// process is still deliberately running). Mirrors processing/'s
// status_server.strict_status_code.
export function strictStatusCode(status: "ok" | "degraded"): number {
  return status === "degraded" ? 503 : 200;
}

function buildStatus(publicConfig: PublicConfig) {
  const bluesky = getBlueskyState();
  const blueskyLabels = getBlueskyLabelsState();
  const mastodon = getInstanceStatus();
  return {
    status: computeStatus(bluesky, blueskyLabels, mastodon),
    bluesky,
    blueskyLabels,
    mastodon,
    pendingExclusionCount: pendingExclusionCount(),
    config: publicConfig,
  };
}

export function startStatusServer(port: number, publicConfig: PublicConfig): void {
  const server = createServer((req, res) => {
    if (req.url !== "/health" && req.url !== "/health/strict") {
      res.writeHead(404).end();
      return;
    }
    const status = buildStatus(publicConfig);
    const code = req.url === "/health/strict" ? strictStatusCode(status.status) : 200;
    res.writeHead(code, { "Content-Type": "application/json" }).end(JSON.stringify(status));
  });
  server.listen(port, () => {
    console.log(`[ingestion] status server listening on :${port}/health`);
  });
}
