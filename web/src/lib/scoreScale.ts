import type { FeedPost, FeedPostScores } from "../api/types";

// Mirrors processing/'s quality_exclude.py QUALITY_EXCLUDE_THRESHOLD -- only
// posts scoring at or above this are ever ranking-eligible, so it's the
// real floor of what reaches /feed. Scaling to [QUALITY_THRESHOLD, 1]
// instead of the theoretical [0, 1] is what makes the quality bar actually
// use its visual range, rather than every post reading as "nearly full"
// against a range whose bottom half never appears in practice.
// Hand-synced, not fetched - processing/'s copy is env-configurable, so
// this can silently drift if that's ever changed without updating this
// too. See the wiki's Web Internals page.
export const QUALITY_THRESHOLD = 0.39;

export function qualityFraction(quality: number | null): number {
  if (quality === null) return 0;
  const fraction = (quality - QUALITY_THRESHOLD) / (1 - QUALITY_THRESHOLD);
  return Math.min(1, Math.max(0, fraction));
}

// recency_decay isn't persisted on its own - base = quality x
// recency_decay(created_at, now-at-scoring-time), so dividing recovers the
// exact decay factor actually applied when this post was scored. Recomputing
// recency_decay fresh from created_at and the current time would give a
// different (more-decayed) number than the one that actually produced this
// post's base/rank, since "now" has moved on since scoring - hence derived,
// not recomputed.
export function deriveRecency(scores: FeedPostScores): number {
  if (scores.quality === null || scores.quality <= 0) return 0;
  return Math.min(1, Math.max(0, scores.base / scores.quality));
}

// Rank has no fixed ceiling or floor (MMR's diversity term can push
// rank_score negative) - unlike quality/recency, there's no absolute scale
// to bar it against. Percentile rank within a fixed comparison set instead:
// fraction of `values` at or below `value`. Not min-max, so one outlier in
// the set can't compress everyone else's bar toward empty.
export function percentileRank(value: number, values: number[]): number {
  if (values.length === 0) return 0;
  const atOrBelow = values.filter((v) => v <= value).length;
  return atOrBelow / values.length;
}

export interface RelativeFractions {
  rank: number;
}

// Computed once per fetched page (20 posts, api/'s default `limit`), not
// recalculated as more pages load -- an ever-growing comparison set would
// mean already-rendered cards' bars silently change length as the user
// scrolls further, with no action of their own. Scoping to the post's own
// page keeps every rendered bar stable once shown, at the cost of "vs. this
// batch" being a snapshot rather than a durable fact about the post.
export function relativeFractions(posts: FeedPost[]): Map<string, RelativeFractions> {
  const rankValues = posts.map((p) => p.scores.rank);

  const result = new Map<string, RelativeFractions>();
  for (const post of posts) {
    result.set(post.id, { rank: percentileRank(post.scores.rank, rankValues) });
  }
  return result;
}
