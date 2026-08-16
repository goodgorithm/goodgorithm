import postgres from "postgres";

import { recordInsert } from "./heartbeat";

const sql = postgres(process.env.DATABASE_URL!, { max: 5 });

export interface RawPost {
  source: "bluesky" | "mastodon";
  source_id: string;
  author_id: string;
  text: string;
  lang: string | null;
  created_at: Date;
  // Mastodon's account.created_at; null for Bluesky (no equivalent
  // concept). Required, not optional, so every call site states that
  // explicitly rather than silently defaulting.
  mastodon_account_created_at: Date | null;
  raw_json: unknown;
}

export async function insertPost(post: RawPost): Promise<void> {
  await sql`
    INSERT INTO raw_posts (
      source, source_id, author_id, text, lang, created_at,
      mastodon_account_created_at, raw_json
    )
    VALUES (
      ${post.source},
      ${post.source_id},
      ${post.author_id},
      ${post.text},
      ${post.lang},
      ${post.created_at},
      ${post.mastodon_account_created_at},
      ${sql.json(post.raw_json as Parameters<typeof sql.json>[0])}
    )
    ON CONFLICT (source, source_id) DO NOTHING
  `;
  // Query succeeding (even a no-op duplicate skip via ON CONFLICT) is
  // evidence the pipeline is actually connected and functioning - that's
  // the signal the heartbeat cares about, not strictly "a new row landed."
  recordInsert();
}

// Used by the labels-stream content filter -- no recordInsert() call,
// deletes aren't the liveness signal the heartbeat tracks. Returns the
// number of rows actually deleted (0 if none matched, e.g. a post we
// never ingested in the first place under BLUESKY_SAMPLE_RATE, or one
// that already aged out via retention).
export async function deleteBySourceId(source: "bluesky" | "mastodon", sourceId: string): Promise<number> {
  const result = await sql`DELETE FROM raw_posts WHERE source = ${source} AND source_id = ${sourceId}`;
  return result.count;
}

// Moderation blocklist -- written by a human moderator directly (SQL) or
// by blueskyLabels.ts's bot-label handling (see the wiki's Content Policy
// page). ON CONFLICT DO NOTHING: the label stream can redeliver the same
// label on reconnect, and an automated write should never overwrite a
// moderator's manual one.
export async function blockAuthor(
  source: "bluesky" | "mastodon",
  authorId: string,
  reason: string,
): Promise<void> {
  await sql`
    INSERT INTO blocked_authors (source, author_id, reason)
    VALUES (${source}, ${authorId}, ${reason})
    ON CONFLICT (source, author_id) DO NOTHING
  `;
}

export async function close(): Promise<void> {
  await sql.end();
}
