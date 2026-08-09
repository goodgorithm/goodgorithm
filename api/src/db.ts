import postgres from "postgres";

import type { Cursor } from "./pagination";

const sql = postgres(process.env.DATABASE_URL!, { max: 5 });

export interface FeedPost {
  id: string;
  source: "bluesky" | "mastodon";
  source_id: string;
  author_id: string;
  text: string;
  created_at: Date;
  entities: string[] | null;
  sentiment_score: number;
  topicality_score: number;
  base_score: number;
  rank_score: number;
  mastodon_permalink: string | null;
  mastodon_display_name: string | null;
  mastodon_avatar_url: string | null;
  bluesky_embed: unknown;
  mastodon_media: unknown;
  mastodon_card: unknown;
  mastodon_sensitive: boolean | null;
  bluesky_labels: unknown;
}

export async function fetchFeed(limit: number, cursor: Cursor | null): Promise<FeedPost[]> {
  const rows = await sql<FeedPost[]>`
    SELECT r.id, r.source, r.source_id, r.author_id, r.text, r.created_at, p.entities,
           p.sentiment_score, p.topicality_score, p.base_score, p.rank_score,
           r.raw_json->>'url' AS mastodon_permalink,
           r.raw_json->'account'->>'display_name' AS mastodon_display_name,
           r.raw_json->'account'->>'avatar' AS mastodon_avatar_url,
           r.raw_json->'commit'->'record'->'embed' AS bluesky_embed,
           r.raw_json->'media_attachments' AS mastodon_media,
           r.raw_json->'card' AS mastodon_card,
           (r.raw_json->>'sensitive')::boolean AS mastodon_sensitive,
           r.raw_json->'commit'->'record'->'labels' AS bluesky_labels
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
