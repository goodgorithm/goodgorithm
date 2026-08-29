import os
import time
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

import config

# No try/except anywhere in this file, deliberately -- unlike Redis (an
# auxiliary signal input dedup/bot_filter/topicality can degrade without),
# a Postgres write here IS the actual deliverable of most pipeline stages
# (upsert_processed_posts, update_rank_scores, mark_moderation_checked,
# purge_blocked_authors, etc.). Silently swallowing a write failure would
# mean a cycle claims success while having done nothing -- a more
# deceptive failure than the loud crash this file's current behavior
# produces instead. A deliberate choice, not an oversight -- see
# CLAUDE.md's Service resilience section and the wiki's Pipeline
# Internals page.

# See the wiki's Pipeline Internals page for what each of these controls.
DB_POOL_MIN_SIZE = int(os.environ.get("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE = int(os.environ.get("DB_POOL_MAX_SIZE", "5"))
if DB_POOL_MIN_SIZE > DB_POOL_MAX_SIZE:
    raise ValueError(f"DB_POOL_MIN_SIZE ({DB_POOL_MIN_SIZE}) must not exceed DB_POOL_MAX_SIZE ({DB_POOL_MAX_SIZE})")

pool = ConnectionPool(config.DATABASE_URL, min_size=DB_POOL_MIN_SIZE, max_size=DB_POOL_MAX_SIZE, open=True)


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
    # Newest-first, not FIFO, and NOT EXISTS rather than LEFT JOIN ...
    # WHERE p.id IS NULL -- both deliberate, neither obvious without
    # production scale. See the wiki's Pipeline Internals page for why.
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
    link_share_penalty: float = 1.0
    generated_thumbnail_url: str | None = None


DB_UPSERT_PROCESSED_POSTS_CHUNK_SIZE = int(os.environ.get("DB_UPSERT_PROCESSED_POSTS_CHUNK_SIZE", "500"))

_PROCESSED_POSTS_COLUMNS = (
    "raw_post_id, dedup_cluster_id, is_dedup_canonical, is_bot, bot_score, "
    "sentiment_score, sentiment_method, topicality_score, entities, "
    "base_score, rank_score, quote_content, category, category_method, "
    "context_penalty, link_share_penalty, generated_thumbnail_url, pipeline_version"
)


# One VALUES row's placeholders, cast to each processed_posts column's type
# so the (VALUES ...) derived table below has unambiguous column types even
# when a whole chunk is all-NULL for a column. Same technique as
# update_rank_scores' own VALUES join.
_PROCESSED_POSTS_ROW_SQL = (
    "(%s::uuid, %s::uuid, %s::boolean, %s::boolean, %s::real, "
    "%s::real, %s::text, %s::real, %s::jsonb, "
    "%s::real, %s::real, %s::jsonb, %s::text, %s::text, "
    "%s::real, %s::real, %s::text, %s::text)"
)


def _build_processed_posts_upsert_sql(row_count: int) -> str:
    """INSERT ... SELECT ... FROM (VALUES ...) WHERE EXISTS(raw_posts) -- not a
    plain multi-row VALUES INSERT. A raw_post can be deleted between run_cycle
    fetching it and this write landing (ingestion/'s blueskyLabels stream
    retroactively deletes a post Bluesky labels adult-content, mid-scoring),
    which would FK-violate on processed_posts_raw_post_id_fkey and -- since
    infra/db.py deliberately has no try/except -- crash-loop the process
    (issue #128). The WHERE EXISTS drops any such vanished row from the batch
    atomically: a moderation-deleted post simply gets no processed_posts row,
    which is correct."""
    values_sql = ", ".join([_PROCESSED_POSTS_ROW_SQL] * row_count)
    return f"""
        INSERT INTO processed_posts ({_PROCESSED_POSTS_COLUMNS})
        SELECT v.* FROM (VALUES {values_sql}) AS v ({_PROCESSED_POSTS_COLUMNS})
        WHERE EXISTS (SELECT 1 FROM raw_posts r WHERE r.id = v.raw_post_id)
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
            link_share_penalty     = EXCLUDED.link_share_penalty,
            generated_thumbnail_url = EXCLUDED.generated_thumbnail_url,
            pipeline_version       = EXCLUDED.pipeline_version,
            processed_at           = NOW()
        """


def upsert_processed_posts(rows: list[ProcessedPostUpsert]) -> None:
    """Bulk-writes a cycle's scored posts in one round trip, not one per
    post. Chunked multi-row rather than one giant statement, so param count
    stays bounded as batch_size grows. See _build_processed_posts_upsert_sql
    for why it's an INSERT ... SELECT ... WHERE EXISTS, not a plain VALUES
    INSERT."""
    if not rows:
        return
    with pool.connection() as conn:
        for i in range(0, len(rows), DB_UPSERT_PROCESSED_POSTS_CHUNK_SIZE):
            chunk = rows[i : i + DB_UPSERT_PROCESSED_POSTS_CHUNK_SIZE]
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
                    row.link_share_penalty,
                    row.generated_thumbnail_url,
                    row.pipeline_version,
                )
            ]
            conn.execute(_build_processed_posts_upsert_sql(len(chunk)), params)


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
    link_share_penalty: float
    source: str
    author_id: str


def fetch_rankable_posts(since: datetime, min_sentiment: float, pool_size: int) -> list[RankableRow]:
    """Pushes filter_eligible's is_bot/is_dedup_canonical/sentiment checks
    and the RANKING_MMR_CANDIDATE_POOL_SIZE cap into SQL, rather than
    fetching every eligible post's full text for the whole time window and
    filtering/capping in Python. ORDER BY p.base_score uses each row's
    previous-cycle value (at most REFRESH_RANKINGS_INTERVAL_SECONDS stale,
    since this same process rewrites it every cycle) as a proxy for this
    cycle's own ranking cutoff -- close enough given how little recency
    decay moves in that window. rank_posts() still re-filters/re-caps in
    Python too, so behavior stays correct even when it's called with an
    arbitrary post list (tests, a REPL) that didn't come through this
    query. See the wiki's Pipeline Internals page."""
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.text, r.created_at, p.sentiment_score, p.topicality_score,
                   p.entities, p.is_bot, p.is_dedup_canonical, p.context_penalty,
                   p.link_share_penalty, r.source, r.author_id
            FROM processed_posts p
            JOIN raw_posts r ON r.id = p.raw_post_id
            WHERE r.created_at >= %s
              AND p.is_bot = false
              AND p.is_dedup_canonical = true
              AND p.sentiment_score >= %s
            ORDER BY p.base_score DESC NULLS LAST
            LIMIT %s
            """,
            (since, min_sentiment, pool_size),
        ).fetchall()
    return [RankableRow(*row) for row in rows]


DB_RANK_SCORE_UPDATE_CHUNK_SIZE = int(os.environ.get("DB_RANK_SCORE_UPDATE_CHUNK_SIZE", "1000"))


def update_rank_scores(updates: list[tuple[UUID, float, float]]) -> None:
    """Bulk-writes (raw_post_id, base_score, rank_score) after MMR ranking.
    refresh_rankings can touch thousands of posts a cycle -- one UPDATE per
    row's per-round-trip latency compounds into minutes at that volume.
    Batched into chunks rather than one giant statement so query
    size/param count stay bounded as the eligible pool grows."""
    if not updates:
        return
    with pool.connection() as conn:
        for i in range(0, len(updates), DB_RANK_SCORE_UPDATE_CHUNK_SIZE):
            chunk = updates[i : i + DB_RANK_SCORE_UPDATE_CHUNK_SIZE]
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


@dataclass
class UncheckedBlueskyPost:
    raw_post_id: UUID
    source_id: str
    author_id: str


def fetch_unchecked_bluesky_posts(batch_size: int) -> list[UncheckedBlueskyPost]:
    """Bounded batch of already-scored Bluesky posts moderation_recheck.py
    hasn't independently re-verified yet -- moderation_recheck.py is a
    backstop against ingestion/'s real-time label-stream listener racing
    Jetstream's own insert. No time window needed -- moderation_checked_at
    is set exactly once and never re-derived, same contract as
    quote_content/generated_thumbnail_url."""
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT p.raw_post_id, r.source_id, r.author_id
            FROM processed_posts p
            JOIN raw_posts r ON r.id = p.raw_post_id
            WHERE r.source = 'bluesky' AND p.moderation_checked_at IS NULL
            ORDER BY r.created_at DESC
            LIMIT %s
            """,
            (batch_size,),
        ).fetchall()
    return [UncheckedBlueskyPost(*row) for row in rows]


def mark_moderation_checked(raw_post_ids: list[UUID]) -> None:
    """Bulk-writes moderation_checked_at = NOW() -- chunked multi-row
    UPDATE, same pattern (and same DB_RANK_SCORE_UPDATE_CHUNK_SIZE) as
    update_rank_scores, not a per-row loop."""
    if not raw_post_ids:
        return
    with pool.connection() as conn:
        for i in range(0, len(raw_post_ids), DB_RANK_SCORE_UPDATE_CHUNK_SIZE):
            chunk = raw_post_ids[i : i + DB_RANK_SCORE_UPDATE_CHUNK_SIZE]
            values_sql = ", ".join(["(%s::uuid)"] * len(chunk))
            conn.execute(
                f"""
                UPDATE processed_posts AS p
                SET moderation_checked_at = NOW()
                FROM (VALUES {values_sql}) AS v(raw_post_id)
                WHERE p.raw_post_id = v.raw_post_id
                """,
                chunk,
            )


@dataclass
class UnresolvedAuthorPost:
    raw_post_id: UUID
    source_id: str
    author_id: str


def fetch_bluesky_posts_needing_author_resolution(batch_size: int) -> list[UnresolvedAuthorPost]:
    """Bounded batch of already-*ranked* Bluesky posts author_resolver.py
    hasn't resolved yet. Deliberately scoped to rank_score IS NOT NULL,
    not every Bluesky post the way fetch_unchecked_bluesky_posts is --
    only a small fraction of ingested Bluesky posts ever get ranked/shown
    at all, so resolving author info for the rest would be pure waste. No
    time window needed -- author_resolved_at is set exactly once and
    never re-derived, same contract as moderation_checked_at."""
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT p.raw_post_id, r.source_id, r.author_id
            FROM processed_posts p
            JOIN raw_posts r ON r.id = p.raw_post_id
            WHERE r.source = 'bluesky' AND p.rank_score IS NOT NULL AND p.author_resolved_at IS NULL
            ORDER BY r.created_at DESC
            LIMIT %s
            """,
            (batch_size,),
        ).fetchall()
    return [UnresolvedAuthorPost(*row) for row in rows]


def mark_authors_resolved(results: list[tuple[UUID, dict | None]]) -> None:
    """Bulk-writes (raw_post_id, bluesky_author) pairs from author_resolver.py's
    sweep. Can't reuse mark_moderation_checked's exact shape -- that writes
    one shared constant (NOW()) to many rows, while each row here carries
    its own distinct JSONB value -- so this is its own chunked multi-row
    UPDATE, same DB_RANK_SCORE_UPDATE_CHUNK_SIZE pattern as
    update_rank_scores/mark_moderation_checked. A `None` bluesky_author is
    a definitive "no author data available" result (mirrors
    moderation_recheck.py's clean-vs-absent contract for a post Bluesky's
    AppView didn't return) -- author_resolved_at is still set either way,
    so a permanently-unresolvable post isn't retried every sweep."""
    if not results:
        return
    with pool.connection() as conn:
        for i in range(0, len(results), DB_RANK_SCORE_UPDATE_CHUNK_SIZE):
            chunk = results[i : i + DB_RANK_SCORE_UPDATE_CHUNK_SIZE]
            values_sql = ", ".join(["(%s::uuid, %s::jsonb)"] * len(chunk))
            params = [
                value
                for raw_post_id, author in chunk
                for value in (raw_post_id, Jsonb(author) if author is not None else None)
            ]
            conn.execute(
                f"""
                UPDATE processed_posts AS p
                SET bluesky_author = v.bluesky_author, author_resolved_at = NOW()
                FROM (VALUES {values_sql}) AS v(raw_post_id, bluesky_author)
                WHERE p.raw_post_id = v.raw_post_id
                """,
                params,
            )


def fetch_blocked_authors() -> set[tuple[str, str]]:
    """Whole table -- the moderation blocklist is small (manual entries +
    Bluesky bot-label auto-inserts), cheaper than a per-post query. Called
    through fetch_moderation_lists()'s cache below, not directly, from
    run_cycle. See CLAUDE.md's Content moderation section."""
    with pool.connection() as conn:
        rows = conn.execute("SELECT source, author_id FROM blocked_authors").fetchall()
    return {(row[0], row[1]) for row in rows}


def fetch_suppressed_terms() -> frozenset[str]:
    """Whole table -- same "cheaper than a per-post query, moderatable
    without a service restart" pattern as fetch_blocked_authors. Called
    through fetch_moderation_lists()'s cache below, not directly, from
    run_cycle. See CLAUDE.md's Content moderation section."""
    with pool.connection() as conn:
        rows = conn.execute("SELECT term FROM suppressed_terms").fetchall()
    return frozenset(row[0] for row in rows)


def fetch_suppressed_domains() -> frozenset[str]:
    """Whole table -- same pattern as fetch_suppressed_terms. Called
    through fetch_moderation_lists()'s cache below, not directly, from
    run_cycle. See CLAUDE.md's Content moderation section."""
    with pool.connection() as conn:
        rows = conn.execute("SELECT domain FROM suppressed_domains").fetchall()
    return frozenset(row[0] for row in rows)


# How long fetch_moderation_lists()'s combined cache stays valid before the
# next call re-queries all three tables. Optional; defaults apply if unset.
# See the wiki's Configuration page.
MODERATION_LISTS_REFRESH_SECONDS = int(os.environ.get("MODERATION_LISTS_REFRESH_SECONDS", "60"))

_moderation_lists_cache: tuple[set[tuple[str, str]], frozenset[str], frozenset[str]] | None = None
_moderation_lists_cached_at = 0.0


def fetch_moderation_lists() -> tuple[set[tuple[str, str]], frozenset[str], frozenset[str]]:
    """Combines the three whole-table reads above into one cached result,
    refreshed at most every MODERATION_LISTS_REFRESH_SECONDS rather than on
    every call. run_cycle() calls this every processing cycle, which under
    a real backlog can run every few seconds (bounded only by
    PROCESSING_BACKLOG_BUFFER_SECONDS) -- re-querying three small,
    rarely-changing tables that often is pure waste. A moderator's edit
    still takes effect within one cache window, not one redeploy, just not
    necessarily on the very next cycle."""
    global _moderation_lists_cache, _moderation_lists_cached_at
    now = time.monotonic()
    if _moderation_lists_cache is None or now - _moderation_lists_cached_at >= MODERATION_LISTS_REFRESH_SECONDS:
        _moderation_lists_cache = (fetch_blocked_authors(), fetch_suppressed_terms(), fetch_suppressed_domains())
        _moderation_lists_cached_at = now
    return _moderation_lists_cache


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
    """Coordinated-bot-network detection -- a full-table aggregate over
    raw_posts, structurally different from every other per-post check in
    this module, deliberately called on a much slower cadence than a
    normal cycle (see main.py). Clusters Mastodon accounts by home domain
    (the part of author_id after '@') whose *real* account creation date
    (Mastodon's own account.created_at, promoted into its own column at
    ingestion time -- not "when we first saw a post from them", which is
    retention-windowed and would look artificially clustered for every
    account regardless of true age) falls within a tight span, with a
    volume floor so a handful of low-activity accounts on a big shared
    instance never gets flagged.

    Reads mastodon_account_created_at directly rather than extracting
    raw_json->'account'->>'created_at' at query time -- that JSON-path
    extraction across the full Mastodon population is too slow at this
    table's scale. Same "promote a frequently-queried field out of raw_json
    into a real column" pattern text/lang/author_id already follow, not a
    workaround. See the wiki's Pipeline Internals page.

    author_id is `{polling_instance}/{acct}` (ingestion/src/mastodon.ts) --
    the same real account seen via more than one of the 8 polled
    instances' public timelines (ActivityPub federation routinely surfaces
    one post through several instances) gets a distinct author_id per
    polling instance, even though `acct` (and so the true identity) is
    identical. Using raw author_id directly would silently inflate both
    account_count and post_count by however many instances a post fanned
    out through. `identity` here strips the polling-instance prefix
    (split_part on '/') so account_count and post_count are deduplicated
    on the real account and the real post (author + text + created_at, not
    source_id, which is itself per-polling-instance) instead. home_domain's
    own derivation is untouched -- split_part on '@' gives the same result
    either way, since '/' always precedes '@' in the raw string.

    author_ids stays un-deduplicated (every raw, polling-instance-prefixed
    variant, not one per identity) deliberately -- blocked_authors matches
    against raw_posts.author_id exactly, so a moderator blocking every
    entry in this list needs each variant to actually exclude that
    account's posts regardless of which polled instance surfaced them."""
    with pool.connection() as conn:
        rows = conn.execute(
            """
            WITH normalized AS (
                SELECT
                    split_part(author_id, '@', 2) AS home_domain,
                    split_part(author_id, '/', 2) AS identity,
                    author_id,
                    text,
                    created_at,
                    mastodon_account_created_at
                FROM raw_posts
                WHERE source = 'mastodon'
                  AND position('@' in author_id) > 0
                  AND mastodon_account_created_at IS NOT NULL
            )
            SELECT
                home_domain,
                array_agg(DISTINCT author_id) AS author_ids,
                COUNT(DISTINCT identity) AS account_count,
                COUNT(DISTINCT (identity, text, created_at)) AS post_count,
                MIN(mastodon_account_created_at) AS earliest_created,
                MAX(mastodon_account_created_at) AS latest_created
            FROM normalized
            GROUP BY home_domain
            HAVING COUNT(DISTINCT identity) >= %s
               AND MAX(mastodon_account_created_at) - MIN(mastodon_account_created_at)
                   <= (%s::text || ' days')::interval
               AND COUNT(DISTINCT (identity, text, created_at)) >= %s
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
