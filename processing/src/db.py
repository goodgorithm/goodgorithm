from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

import config

pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=5, open=True)


@dataclass
class RawPost:
    id: UUID
    source: str
    source_id: str
    author_id: str
    text: str
    lang: str | None
    created_at: datetime
    raw_json: dict


def fetch_unprocessed_posts(batch_size: int) -> list[RawPost]:
    # Newest-first, not FIFO: confirmed 2026-08-10 that oldest-first plus a
    # deep backlog (ingestion outpacing processing) means processing spends
    # all its time on posts already at the 24h retention edge - they get a
    # rank_score and are cascade-deleted by cleanup_old_data() moments
    # later, before /feed can ever see them. Newest-first guarantees fresh
    # content always gets processed first; a post that never gets reached
    # before it ages out was never going to make a useful feed entry
    # anyway (MMR's recency_decay would have suppressed it too).
    #
    # NOT EXISTS, not LEFT JOIN ... WHERE p.id IS NULL: confirmed 2026-08-11
    # that at real production scale (250k+ raw_posts) the LEFT JOIN form
    # crash-looped processing for ~22h straight (QueryCanceled: statement
    # timeout). The planner badly misestimates that anti-join's selectivity
    # (EXPLAIN showed `rows=1` at every level) and picks a full Parallel
    # Seq Scan + Hash Join + Sort over both tables instead of walking
    # raw_posts_created_at_idx newest-first and stopping at LIMIT. NOT
    # EXISTS gives the planner a much clearer anti-join signal - confirmed
    # via EXPLAIN against production that it correctly picks a Nested Loop
    # Anti Join over raw_posts_created_at_idx +
    # processed_posts_raw_post_id_key (index-only), ~27x cheaper by the
    # planner's own cost estimate. Same result set, same ORDER BY/LIMIT.
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.source, r.source_id, r.author_id, r.text, r.lang, r.created_at, r.raw_json
            FROM raw_posts r
            WHERE NOT EXISTS (
                SELECT 1 FROM processed_posts p WHERE p.raw_post_id = r.id
            )
            ORDER BY r.created_at DESC
            LIMIT %s
            """,
            (batch_size,),
        ).fetchall()
    return [RawPost(*row) for row in rows]


@dataclass
class ProcessedPostUpsert:
    raw_post_id: UUID
    dedup_cluster_id: UUID
    sentiment_score: float
    sentiment_method: str
    topicality_score: float
    pipeline_version: str
    is_dedup_canonical: bool = True
    is_bot: bool = False
    bot_score: float | None = None
    entities: list | None = None
    base_score: float | None = None
    rank_score: float | None = None
    quote_content: dict | None = None
    category: str | None = None
    category_method: str | None = None
    context_penalty: float = 1.0
    generated_thumbnail_url: str | None = None


UPSERT_PROCESSED_POSTS_CHUNK_SIZE = 500


def upsert_processed_posts(rows: list[ProcessedPostUpsert]) -> None:
    """Batched sibling of the old per-post upsert -- run_cycle used to call
    that once per post (up to batch_size separate round trips every cycle,
    2026-08-11 perf pass). Mirrors update_rank_scores' existing chunked-
    multi-row-VALUES pattern below rather than one giant statement, so
    param count stays bounded as batch_size grows."""
    if not rows:
        return
    with pool.connection() as conn:
        for i in range(0, len(rows), UPSERT_PROCESSED_POSTS_CHUNK_SIZE):
            chunk = rows[i : i + UPSERT_PROCESSED_POSTS_CHUNK_SIZE]
            values_sql = ", ".join(
                ["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(chunk)
            )
            params = [
                value
                for row in chunk
                for value in (
                    row.raw_post_id,
                    row.dedup_cluster_id,
                    row.is_dedup_canonical,
                    row.is_bot,
                    row.bot_score,
                    row.sentiment_score,
                    row.sentiment_method,
                    row.topicality_score,
                    Jsonb(row.entities) if row.entities is not None else None,
                    row.base_score,
                    row.rank_score,
                    Jsonb(row.quote_content) if row.quote_content is not None else None,
                    row.category,
                    row.category_method,
                    row.context_penalty,
                    row.generated_thumbnail_url,
                    row.pipeline_version,
                )
            ]
            conn.execute(
                f"""
                INSERT INTO processed_posts (
                    raw_post_id, dedup_cluster_id, is_dedup_canonical, is_bot, bot_score,
                    sentiment_score, sentiment_method, topicality_score, entities,
                    base_score, rank_score, quote_content, category, category_method,
                    context_penalty, generated_thumbnail_url, pipeline_version
                )
                VALUES {values_sql}
                ON CONFLICT (raw_post_id) DO UPDATE SET
                    dedup_cluster_id       = EXCLUDED.dedup_cluster_id,
                    is_dedup_canonical     = EXCLUDED.is_dedup_canonical,
                    is_bot                 = EXCLUDED.is_bot,
                    bot_score              = EXCLUDED.bot_score,
                    sentiment_score        = EXCLUDED.sentiment_score,
                    sentiment_method       = EXCLUDED.sentiment_method,
                    topicality_score       = EXCLUDED.topicality_score,
                    entities               = EXCLUDED.entities,
                    base_score             = EXCLUDED.base_score,
                    rank_score             = EXCLUDED.rank_score,
                    quote_content          = EXCLUDED.quote_content,
                    category               = EXCLUDED.category,
                    category_method        = EXCLUDED.category_method,
                    context_penalty        = EXCLUDED.context_penalty,
                    generated_thumbnail_url = EXCLUDED.generated_thumbnail_url,
                    pipeline_version       = EXCLUDED.pipeline_version,
                    processed_at           = NOW()
                """,
                params,
            )


@dataclass
class RankableRow:
    raw_post_id: UUID
    text: str
    created_at: datetime
    sentiment_score: float
    topicality_score: float
    entities: list
    is_bot: bool
    is_dedup_canonical: bool
    context_penalty: float


def fetch_rankable_posts(since: datetime) -> list[RankableRow]:
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.text, r.created_at, p.sentiment_score, p.topicality_score,
                   p.entities, p.is_bot, p.is_dedup_canonical, p.context_penalty
            FROM processed_posts p
            JOIN raw_posts r ON r.id = p.raw_post_id
            WHERE r.created_at >= %s
            """,
            (since,),
        ).fetchall()
    return [RankableRow(*row) for row in rows]


RANK_SCORE_UPDATE_CHUNK_SIZE = 1000


def update_rank_scores(updates: list[tuple[UUID, float, float]]) -> None:
    """Bulk-writes (raw_post_id, base_score, rank_score) after MMR ranking.

    refresh_rankings can touch thousands of posts a cycle (the eligible
    window isn't bounded to a handful of rows - it's whatever passed the
    bot/dedup/sentiment filters in the last MMR_WINDOW_HOURS). One UPDATE
    per row was the actual production crash: even a modest per-round-trip
    latency compounds into minutes at that volume, all inside a single
    process cycle with nothing else able to run. Batched into chunks
    rather than one giant statement so query size/param count stay
    bounded as the eligible pool grows.
    """
    if not updates:
        return
    with pool.connection() as conn:
        for i in range(0, len(updates), RANK_SCORE_UPDATE_CHUNK_SIZE):
            chunk = updates[i : i + RANK_SCORE_UPDATE_CHUNK_SIZE]
            values_sql = ", ".join(["(%s::uuid, %s::real, %s::real)"] * len(chunk))
            params = [value for row in chunk for value in row]
            conn.execute(
                f"""
                UPDATE processed_posts AS p
                SET base_score = v.base_score, rank_score = v.rank_score
                FROM (VALUES {values_sql}) AS v(raw_post_id, base_score, rank_score)
                WHERE p.raw_post_id = v.raw_post_id
                """,
                params,
            )


def delete_old_raw_posts(cutoff: datetime) -> int:
    """processed_posts rows cascade-delete automatically (FK ON DELETE
    CASCADE, see migration 0003)."""
    with pool.connection() as conn:
        cur = conn.execute("DELETE FROM raw_posts WHERE created_at < %s", (cutoff,))
        return cur.rowcount


def delete_raw_post(post_id: UUID) -> bool:
    """Single-row sibling of delete_old_raw_posts, for content-filter
    exclusions. Same cascade behavior. Returns whether a row was actually
    deleted (it may already be gone, e.g. aged out by retention)."""
    with pool.connection() as conn:
        cur = conn.execute("DELETE FROM raw_posts WHERE id = %s", (post_id,))
        return cur.rowcount > 0


def fetch_blocked_authors() -> set[tuple[str, str]]:
    """Whole table, loaded fresh once per cycle -- moderation blocklist
    (issue #7) is small (manual entries + Bluesky bot-label auto-inserts),
    cheaper than a per-post query."""
    with pool.connection() as conn:
        rows = conn.execute("SELECT source, author_id FROM blocked_authors").fetchall()
    return {(row[0], row[1]) for row in rows}


def fetch_suppressed_terms() -> frozenset[str]:
    """Whole table, loaded fresh once per cycle -- same "cheaper than a
    per-post query, no caching/TTL, moderatable without a service restart"
    pattern as fetch_blocked_authors (issue #7). Moderator-curated term
    list (issue #39): a moderator adds/removes rows directly via the
    Supabase SQL editor, no admin UI/CLI, same precedent."""
    with pool.connection() as conn:
        rows = conn.execute("SELECT term FROM suppressed_terms").fetchall()
    return frozenset(row[0] for row in rows)


def purge_blocked_authors() -> int:
    """Deletes any already-ingested raw_posts (processed_posts cascades)
    for a blocklisted (source, author_id) -- run every cycle so a new
    blocklist entry (manual or the bot-label auto-insert) takes effect on
    posts already in the DB within one cycle, not just future ones."""
    with pool.connection() as conn:
        cur = conn.execute(
            """
            DELETE FROM raw_posts r
            USING blocked_authors b
            WHERE r.source = b.source AND r.author_id = b.author_id
            """
        )
        return cur.rowcount


@dataclass
class ClusterCandidate:
    home_domain: str
    author_ids: list[str]
    account_count: int
    post_count: int
    earliest_account_created_at: datetime
    latest_account_created_at: datetime


def fetch_cluster_candidates(
    min_accounts: int, max_creation_span_days: int, min_post_count: int
) -> list[ClusterCandidate]:
    """Coordinated-bot-network detection (issue #44) -- a full-table
    aggregate over raw_posts, structurally different from every other
    per-post check in this module, deliberately called on a much slower
    cadence than a normal cycle (see main.py). Clusters Mastodon accounts
    by home domain (the part of author_id after '@') whose *real* account
    creation date (Mastodon's own account.created_at, promoted into its
    own column at ingestion time -- see mastodon_account_created_at's
    migration -- not "when we first saw a post from them", which is
    retention-windowed and would look artificially clustered for every
    account regardless of true age) falls within a tight span, with a
    volume floor so a handful of low-activity accounts on a big shared
    instance never gets flagged.

    Reads mastodon_account_created_at directly rather than extracting
    raw_json->'account'->>'created_at' at query time -- that JSON-path
    extraction across the full ~220k-row Mastodon population timed out
    in production (confirmed 2026-08-15), the same class of problem
    CLAUDE.md documents for a similar raw_json ilike scan. This is the
    fix, not a workaround: same "promote a frequently-queried field out
    of raw_json into a real column" pattern text/lang/author_id already
    follow."""
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT
                split_part(author_id, '@', 2) AS home_domain,
                array_agg(DISTINCT author_id) AS author_ids,
                COUNT(DISTINCT author_id) AS account_count,
                COUNT(*) AS post_count,
                MIN(mastodon_account_created_at) AS earliest_created,
                MAX(mastodon_account_created_at) AS latest_created
            FROM raw_posts
            WHERE source = 'mastodon'
              AND position('@' in author_id) > 0
              AND mastodon_account_created_at IS NOT NULL
            GROUP BY home_domain
            HAVING COUNT(DISTINCT author_id) >= %s
               AND MAX(mastodon_account_created_at) - MIN(mastodon_account_created_at)
                   <= (%s::text || ' days')::interval
               AND COUNT(*) >= %s
            """,
            (min_accounts, max_creation_span_days, min_post_count),
        ).fetchall()
    return [ClusterCandidate(*row) for row in rows]


def upsert_flagged_clusters(candidates: list[ClusterCandidate]) -> None:
    """Refreshes flagged_author_clusters from the latest detect_clusters()
    pass. ON CONFLICT deliberately never touches dismissed_at -- a
    moderator's dismissal of a false positive survives a later refresh
    (the cluster's counts still update) rather than silently re-appearing
    every run."""
    if not candidates:
        return
    with pool.connection() as conn:
        for c in candidates:
            conn.execute(
                """
                INSERT INTO flagged_author_clusters (
                    home_domain, author_ids, account_count, post_count,
                    earliest_account_created_at, latest_account_created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (home_domain) DO UPDATE SET
                    author_ids                  = EXCLUDED.author_ids,
                    account_count                = EXCLUDED.account_count,
                    post_count                   = EXCLUDED.post_count,
                    earliest_account_created_at  = EXCLUDED.earliest_account_created_at,
                    latest_account_created_at    = EXCLUDED.latest_account_created_at,
                    updated_at                   = NOW()
                """,
                (
                    c.home_domain,
                    c.author_ids,
                    c.account_count,
                    c.post_count,
                    c.earliest_account_created_at,
                    c.latest_account_created_at,
                ),
            )


def close() -> None:
    pool.close()
