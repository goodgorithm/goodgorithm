import { parseNumberEnv } from "./env";

// bluesky.ts's Jetstream-driven raw_posts INSERT and blueskyLabels.ts's
// label-stream-driven DELETE are two independent WebSocket connections in
// this same process with no coordination. When Bluesky's own moderation
// labeler reacts fast enough that its label arrives before our own insert
// has landed, blueskyLabels.ts's DELETE finds no matching row -- and since
// it's a one-shot attempt with no retry, the post would otherwise survive
// once the insert completes moments later. This module is the shared
// state that closes that ordering: blueskyLabels.ts records a miss here,
// bluesky.ts checks it right before inserting.
//
// Bounded window for that flipped ordering only -- real insert-latency
// gaps run a few seconds, so 30s gives real headroom. The opposite
// ordering (insert lands first, label arrives after) already works via
// the existing deleteBySourceId path and needs no change.
const BLUESKY_PENDING_EXCLUSION_TTL_MS = parseNumberEnv("BLUESKY_PENDING_EXCLUSION_TTL_MS", 30000);

// sourceId -> expiry epoch ms. Only ever grows from markPendingExclusion's
// misses (the "no matching row" case) and shrinks via consumption or the
// opportunistic sweep below -- no separate timer needed. Steady-state size
// is bounded by (real adult-label arrival rate) x TTL, on the order of
// tens of entries given production's observed ~1/sec label rate.
const pending = new Map<string, number>();

function sweepExpired(now: number): void {
  for (const [key, expiresAt] of pending) {
    if (expiresAt <= now) pending.delete(key);
  }
}

// Called by blueskyLabels.ts only when deleteBySourceId found 0 rows --
// remembers this post as "should never be inserted" for a bounded window.
export function markPendingExclusion(sourceId: string, now: number = Date.now()): void {
  sweepExpired(now); // opportunistic cleanup, piggybacked on the write path
  pending.set(sourceId, now + BLUESKY_PENDING_EXCLUSION_TTL_MS);
}

// Called by bluesky.ts right before insertPost. Consumes (deletes) the
// entry either way so a stale/expired one can't linger or be reused.
export function consumePendingExclusion(sourceId: string, now: number = Date.now()): boolean {
  const expiresAt = pending.get(sourceId);
  if (expiresAt === undefined) return false;
  pending.delete(sourceId);
  return expiresAt > now;
}

export function pendingExclusionCount(): number {
  return pending.size;
}

// Test-only: module state is a singleton, so tests need to reset between
// cases without relying on distinct sourceIds everywhere.
export function _clearPendingExclusionsForTests(): void {
  pending.clear();
}
