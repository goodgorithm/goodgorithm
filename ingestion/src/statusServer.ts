import { createServer } from "http";
import { getConnectionState as getBlueskyState } from "./bluesky";
import { getConnectionState as getBlueskyLabelsState } from "./blueskyLabels";
import { parseNumberEnv } from "./env";
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

// Fraction of currently-polled Mastodon instances that must be erroring for
// the whole verdict to flip to "degraded". Default 1.0 = every instance --
// i.e. only a systemic polling failure (loop wedged, host network, a bad
// MASTODON_INSTANCES) counts, not the routine churn of one or two public
// instances 5xx'ing or going down for maintenance. Set 0.5 for
// "majority". A single flaky instance is still visible in /health's
// per-instance `mastodon` map; it just isn't "degraded".
export const MASTODON_DEGRADED_ERROR_RATIO = parseNumberEnv("MASTODON_DEGRADED_ERROR_RATIO", 1);
if (MASTODON_DEGRADED_ERROR_RATIO <= 0 || MASTODON_DEGRADED_ERROR_RATIO > 1) {
  throw new Error(`MASTODON_DEGRADED_ERROR_RATIO must be in (0, 1], got ${MASTODON_DEGRADED_ERROR_RATIO}`);
}

// A poll whose most recent attempt errored -- previously worked and then
// started failing, or every attempt so far has failed. A never-polled
// instance (neither timestamp) is not counted either way.
function isCurrentlyErroring(status: InstanceStatus): boolean {
  return Boolean(status.lastErrorAt) && (!status.lastSuccessAt || status.lastErrorAt! > status.lastSuccessAt);
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
  mastodonErrorRatio: number = MASTODON_DEGRADED_ERROR_RATIO,
): "ok" | "degraded" {
  if (!bluesky.connected) return "degraded";
  if (!blueskyLabels.disabled && !blueskyLabels.connected) return "degraded";

  const instances = Object.values(mastodon);
  const erroring = instances.filter(isCurrentlyErroring).length;
  if (erroring > 0 && erroring / instances.length >= mastodonErrorRatio) {
    return "degraded";
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
