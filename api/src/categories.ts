// The fixed 8-category taxonomy assigned by processing/'s taxonomy.py.
// Hand-duplicated in web/src/api/types.ts -- no shared package across the
// API/web boundary in this repo (same pattern as the Attachment union).
export const CATEGORIES = [
  "technology",
  "arts_culture",
  "animals",
  "science_discovery",
  "kindness_community",
  "environment_nature",
  "health_recovery",
  "sports_achievement",
] as const;

export type Category = (typeof CATEGORIES)[number];
