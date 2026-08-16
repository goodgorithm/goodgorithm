// Dead-man's-switch heartbeat (e.g. a Healthchecks.io check URL): ingestion
// is event-driven (WebSocket + polling), not cyclic like processing/, so
// there's no natural "end of a successful cycle" to hook a ping onto.
// Instead, ping periodically, but only if at least one post was actually
// inserted (from either source) since the last check - a quiet window with
// zero inserts is exactly the failure mode this exists to catch (e.g. the
// Jetstream WebSocket died without reconnecting, or both sources stalled).

const HEARTBEAT_INTERVAL_MS = Number(process.env.HEARTBEAT_INTERVAL_MS ?? "300000");

let insertsSinceLastCheck = 0;

export function recordInsert(): void {
  insertsSinceLastCheck++;
}

// Exported separately from startHeartbeat so it's callable directly - the
// setInterval wrapper isn't itself worth unit-testing, but this is.
export async function checkAndPing(url: string): Promise<void> {
  if (insertsSinceLastCheck === 0) return;
  insertsSinceLastCheck = 0;

  try {
    await fetch(url);
  } catch (err) {
    console.warn("[ingestion] heartbeat ping failed:", (err as Error).message);
  }
}

export function startHeartbeat(url: string | undefined, intervalMs = HEARTBEAT_INTERVAL_MS): void {
  if (!url) return;
  setInterval(() => {
    void checkAndPing(url);
  }, intervalMs);
}
