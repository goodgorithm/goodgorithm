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
  quote_content: unknown;
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
           r.raw_json->'commit'->'record'->'labels' AS bluesky_labels,
           p.quote_content
    FROM processed_posts p
    JOIN raw_posts r ON r.id = p.raw_post_id
    WHERE p.rank_score IS NOT NULL
      ${cursor ? sql`AND (p.rank_score, r.id) < (${cursor.rank_score}, ${cursor.id})` : sql``}
    ORDER BY p.rank_score DESC, r.id DESC
    LIMIT ${limit}
  `;
  return rows;
}

// Cheap enough to run on every /health hit (rate-limited to 100/min anyway)
// - a real check, not just "the Node process is alive," since an external
// uptime monitor watching this endpoint needs it to actually mean something.
// Explicitly bounded: an unreachable DB should fail this check quickly, not
// hang for postgres.js's default ~30s connect_timeout - a health check that
// takes half a minute to say "unhealthy" is nearly as useless as one that
// never answers.
const HEALTH_CHECK_TIMEOUT_MS = 3000;

export async function checkDatabaseConnection(): Promise<boolean> {
  try {
    await Promise.race([
      sql`SELECT 1`,
      new Promise((_, reject) => setTimeout(() => reject(new Error("health check timeout")), HEALTH_CHECK_TIMEOUT_MS)),
    ]);
    return true;
  } catch {
    return false;
  }
}

export async function close(): Promise<void> {
  await sql.end();
}
