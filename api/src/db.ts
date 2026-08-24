import postgres from "postgres";

import type { Cursor } from "./pagination";

// See the wiki's Configuration page.
const DB_POOL_MAX_SIZE = Number(process.env.DB_POOL_MAX_SIZE ?? 5);

const sql = postgres(process.env.DATABASE_URL!, { max: DB_POOL_MAX_SIZE });

// The raw DB row shape this query returns - distinct from types.ts's
// FeedPost (the public /feed response shape), which is assembled from this
// plus buildAttachments()'s output in routes/feed.ts. Named differently on
// purpose to avoid the two colliding.
export interface FeedRow {
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
  pipeline_version: string;
  mastodon_permalink: string | null;
  mastodon_display_name: string | null;
  mastodon_avatar_url: string | null;
  // Bluesky's own AppView-resolved author (issue #73) - Jetstream's firehose
  // never carries this, unlike Mastodon's raw_json which embeds it for free.
  // NULL for Mastodon rows (which don't need it) and for not-yet-swept or
  // unresolvable Bluesky rows. Exactly one of the mastodon_/bluesky_author_*
  // pairs is ever non-null per row, by source - see feed.ts's coalesce.
  bluesky_author_display_name: string | null;
  bluesky_author_avatar_url: string | null;
  // Mastodon's custom-emoji shortcode data (issue #77) - see emoji.ts's
  // buildEmojis. Always null/absent for Bluesky rows, which have no
  // equivalent concept - db.ts never selects a Bluesky counterpart.
  mastodon_account_emojis: unknown;
  mastodon_status_emojis: unknown;
  bluesky_embed: unknown;
  mastodon_media: unknown;
  mastodon_card: unknown;
  mastodon_sensitive: boolean | null;
  bluesky_labels: unknown;
  quote_content: unknown;
  category: string | null;
  generated_thumbnail_url: string | null;
}

export async function fetchFeed(
  limit: number,
  cursor: Cursor | null,
  category: string | null,
): Promise<FeedRow[]> {
  const rows = await sql<FeedRow[]>`
    SELECT r.id, r.source, r.source_id, r.author_id, r.text, r.created_at, p.entities,
           p.sentiment_score, p.topicality_score, p.base_score, p.rank_score,
           p.pipeline_version,
           r.raw_json->>'url' AS mastodon_permalink,
           r.raw_json->'account'->>'display_name' AS mastodon_display_name,
           r.raw_json->'account'->>'avatar' AS mastodon_avatar_url,
           p.bluesky_author->>'displayName' AS bluesky_author_display_name,
           p.bluesky_author->>'avatarUrl' AS bluesky_author_avatar_url,
           r.raw_json->'account'->'emojis' AS mastodon_account_emojis,
           r.raw_json->'emojis' AS mastodon_status_emojis,
           r.raw_json->'commit'->'record'->'embed' AS bluesky_embed,
           r.raw_json->'media_attachments' AS mastodon_media,
           r.raw_json->'card' AS mastodon_card,
           (r.raw_json->>'sensitive')::boolean AS mastodon_sensitive,
           r.raw_json->'commit'->'record'->'labels' AS bluesky_labels,
           p.quote_content,
           p.category,
           p.generated_thumbnail_url
    FROM processed_posts p
    JOIN raw_posts r ON r.id = p.raw_post_id
    WHERE p.rank_score IS NOT NULL
      ${cursor ? sql`AND (p.rank_score, r.id) < (${cursor.rank_score}, ${cursor.id})` : sql``}
      ${category ? sql`AND p.category = ${category}` : sql``}
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
// never answers. See the wiki's Configuration page.
const HEALTH_CHECK_TIMEOUT_MS = Number(process.env.HEALTH_CHECK_TIMEOUT_MS ?? 3000);

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
