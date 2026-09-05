import postgres from "postgres";

import { parseNumberEnv } from "./env";
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

// Forward blocked-author skip. processing/'s run_cycle already
// checks blocked_authors before scoring; this is a cheap ingestion-time
// early-out so a still-active blocked author's ongoing stream never enters
// raw_posts at all (the aggregator/spam-bot case), mirroring
// isBridgedAccount's early-out but DB-backed instead of hardcoded.
// processing/ stays authoritative and purge_blocked_authors still handles
// the retroactive case (a newly-blocked author's already-ingested rows).

// Same knob processing/'s fetch_moderation_lists cache uses -- how long a
// blocked_authors snapshot stays valid before the next read re-queries. A
// moderator's SQL edit still takes effect within one window.
const MODERATION_LISTS_REFRESH_MS = parseNumberEnv("MODERATION_LISTS_REFRESH_SECONDS", 60) * 1000;

// (source, author_id) pairs keyed "source\tauthor_id" -- a tab can't appear
// in a Bluesky DID or a Mastodon "{instance}/{acct}". null until the first
// fetch settles; blockedAuthorsInFlight coalesces the concurrent callers a
// high-rate firehose produces before that first query resolves.
let blockedAuthorsCache: Set<string> | null = null;
let blockedAuthorsCachedAt = 0;
let blockedAuthorsInFlight: Promise<Set<string>> | null = null;

export function blockedAuthorsCacheStale(cachedAt: number, now: number): boolean {
  return now - cachedAt >= MODERATION_LISTS_REFRESH_MS;
}

// The whole (small) moderation blocklist, cached in-process for
// MODERATION_LISTS_REFRESH_MS. This is ingestion/'s only DB *read*. It
// fails OPEN on any query error -- serve the last good snapshot, or an
// empty set on a cold start -- because processing/'s own blocked_authors
// check is the authoritative one: a stale or missing blocklist here just
// means a post is caught one stage later, at processing/'s authoritative check.
// cachedAt is bumped even on failure so a sustained DB outage doesn't
// re-query on every ingested message.
export async function getBlockedAuthors(now: number = Date.now()): Promise<Set<string>> {
  if (blockedAuthorsCache !== null && !blockedAuthorsCacheStale(blockedAuthorsCachedAt, now)) {
    return blockedAuthorsCache;
  }
  if (blockedAuthorsInFlight !== null) return blockedAuthorsInFlight;

  blockedAuthorsInFlight = (async () => {
    try {
      const rows = await sql<{ source: string; author_id: string }[]>`
        SELECT source, author_id FROM blocked_authors
      `;
      blockedAuthorsCache = new Set(rows.map((r) => `${r.source}\t${r.author_id}`));
    } catch (err) {
      console.error(
        "[ingestion] blocked_authors refresh failed, using stale snapshot:",
        (err as Error).message,
      );
      blockedAuthorsCache ??= new Set();
    } finally {
      blockedAuthorsCachedAt = now;
      blockedAuthorsInFlight = null;
    }
    return blockedAuthorsCache as Set<string>;
  })();

  return blockedAuthorsInFlight;
}

// Pure membership test -- key encoding must match getBlockedAuthors above.
export function isBlockedAuthor(source: string, authorId: string, blocked: Set<string>): boolean {
  return blocked.has(`${source}\t${authorId}`);
}

export async function close(): Promise<void> {
  await sql.end();
}
