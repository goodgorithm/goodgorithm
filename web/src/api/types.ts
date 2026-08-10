export type Source = "bluesky" | "mastodon";

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
}

export interface FeedResponse {
  posts: FeedPost[];
  next_cursor: string | null;
}

export interface HealthResponse {
  status: string;
}
