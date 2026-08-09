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
  | { kind: "quote"; url: string };

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
