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
}

export interface FeedResponse {
  posts: FeedPost[];
  next_cursor: string | null;
}

export interface HealthResponse {
  status: string;
}
