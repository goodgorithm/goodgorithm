import postgres from "postgres";

import type { Cursor } from "./pagination";

const sql = postgres(process.env.DATABASE_URL!, { max: 5 });

export interface FeedPost {
  id: string;
  source: "bluesky" | "mastodon";
  author_id: string;
  text: string;
  created_at: Date;
  entities: string[] | null;
  sentiment_score: number;
  topicality_score: number;
  base_score: number;
  rank_score: number;
}

export async function fetchFeed(limit: number, cursor: Cursor | null): Promise<FeedPost[]> {
  const rows = await sql<FeedPost[]>`
    SELECT r.id, r.source, r.author_id, r.text, r.created_at, p.entities,
           p.sentiment_score, p.topicality_score, p.base_score, p.rank_score
    FROM processed_posts p
    JOIN raw_posts r ON r.id = p.raw_post_id
    WHERE p.rank_score IS NOT NULL
      ${cursor ? sql`AND (p.rank_score, r.id) < (${cursor.rank_score}, ${cursor.id})` : sql``}
    ORDER BY p.rank_score DESC, r.id DESC
    LIMIT ${limit}
  `;
  return rows;
}

export async function close(): Promise<void> {
  await sql.end();
}
