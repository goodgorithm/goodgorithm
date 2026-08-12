import type { FeedPost } from "../api/types";

// Mirrors processing/src/ranking.py's POSITIVITY_THRESHOLD -- only posts
// scoring at or above this are ever ranking-eligible, so it's the real
// floor of what reaches /feed. Scaling to [POSITIVITY_THRESHOLD, 1] instead
// of the theoretical [-1, 1] is what makes the sentiment bar actually use
// its visual range, rather than every post reading as "nearly full" against
// a range whose bottom half never appears in practice.
export const POSITIVITY_THRESHOLD = 0.3;

export function sentimentFraction(sentiment: number): number {
  const fraction = (sentiment - POSITIVITY_THRESHOLD) / (1 - POSITIVITY_THRESHOLD);
  return Math.min(1, Math.max(0, fraction));
}

// Topicality/base/rank have no fixed ceiling (topicality is an unbounded
// TF-IDF weight; base/rank compound from it) -- unlike sentiment, there's
// no absolute scale to bar them against. Percentile rank within a fixed
// comparison set instead: fraction of `values` at or below `value`. Not
// min-max, so one outlier in the set can't compress everyone else's bar
// toward empty.
export function percentileRank(value: number, values: number[]): number {
  if (values.length === 0) return 0;
  const atOrBelow = values.filter((v) => v <= value).length;
  return atOrBelow / values.length;
}

export interface RelativeFractions {
  topicality: number;
  base: number;
  rank: number;
}

// Computed once per fetched page (20 posts, api/'s default `limit`), not
// recalculated as more pages load -- an ever-growing comparison set would
// mean already-rendered cards' bars silently change length as the user
// scrolls further, with no action of their own. Scoping to the post's own
// page keeps every rendered bar stable once shown, at the cost of "vs. this
// batch" being a snapshot rather than a durable fact about the post (unlike
// the sentiment bar, which means the same thing every time).
export function relativeFractions(posts: FeedPost[]): Map<string, RelativeFractions> {
  const topicalityValues = posts.map((p) => p.scores.topicality);
  const baseValues = posts.map((p) => p.scores.base);
  const rankValues = posts.map((p) => p.scores.rank);

  const result = new Map<string, RelativeFractions>();
  for (const post of posts) {
    result.set(post.id, {
      topicality: percentileRank(post.scores.topicality, topicalityValues),
      base: percentileRank(post.scores.base, baseValues),
      rank: percentileRank(post.scores.rank, rankValues),
    });
  }
  return result;
}
