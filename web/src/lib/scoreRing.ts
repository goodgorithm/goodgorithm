// Mirrors processing/src/ranking.py's POSITIVITY_THRESHOLD -- only posts
// scoring at or above this are ever ranking-eligible, so it's the real
// floor of what reaches /feed. Scaling the ring to [POSITIVITY_THRESHOLD, 1]
// instead of the theoretical [-1, 1] is what makes it actually use its
// visual range, rather than every post reading as "nearly full" against a
// range whose bottom half never appears in practice.
export const POSITIVITY_THRESHOLD = 0.3;

export function sentimentFraction(sentiment: number): number {
  const fraction = (sentiment - POSITIVITY_THRESHOLD) / (1 - POSITIVITY_THRESHOLD);
  return Math.min(1, Math.max(0, fraction));
}
