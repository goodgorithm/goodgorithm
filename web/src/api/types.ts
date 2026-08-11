export type Source = "bluesky" | "mastodon";

// The fixed 8-category taxonomy assigned by processing/'s taxonomy.py.
// Hand-duplicated in api/src/categories.ts -- no shared package across the
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

export const CATEGORY_LABELS: Record<Category, string> = {
  technology: "Technology",
  arts_culture: "Arts & Culture",
  animals: "Animals",
  science_discovery: "Science & Discovery",
  kindness_community: "Kindness & Community",
  environment_nature: "Environment & Nature",
  health_recovery: "Health & Recovery",
  sports_achievement: "Sports & Achievement",
};

export interface FeedPostScores {
  sentiment: number;
  topicality: number;
  base: number;
  rank: number;
}

export interface FeedPostAuthor {
  display_name: string | null;
  avatar_url: string | null;
}

// Mirrors api/src/attachments.ts's QuoteContent exactly (hand-kept-in-sync,
// no shared package across the API/web boundary).
export type QuoteContent =
  | {
      status: "available";
      author: { displayName: string | null; handle: string | null; avatarUrl: string | null };
      text: string;
      createdAt: string | null;
    }
  | { status: "unavailable"; reason: "not_found" | "filtered" };

export type Attachment =
  | {
      kind: "image";
      thumbnailUrl: string;
      fullUrl: string;
      alt: string | null;
      width: number | null;
      height: number | null;
    }
  | {
      kind: "link";
      url: string;
      title: string | null;
      description: string | null;
      thumbnailUrl: string | null;
      providerName: string | null;
    }
  | {
      kind: "video";
      playlistUrl: string;
      thumbnailUrl: string | null;
      isGif: boolean;
      width: number | null;
      height: number | null;
    }
  | { kind: "quote"; url: string; content: QuoteContent | null };

export interface FeedPost {
  id: string;
  source: Source;
  author_id: string;
  text: string;
  created_at: string;
  entities: string[];
  permalink: string;
  author: FeedPostAuthor;
  scores: FeedPostScores;
  attachments: Attachment[];
  sensitive: boolean;
  category: Category | null;
}

export interface FeedResponse {
  posts: FeedPost[];
  next_cursor: string | null;
}

export interface HealthResponse {
  status: string;
}
