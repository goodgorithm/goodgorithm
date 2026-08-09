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


def fetch_unprocessed_posts(batch_size: int) -> list[RawPost]:
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.source, r.source_id, r.author_id, r.text, r.lang, r.created_at
            FROM raw_posts r
            LEFT JOIN processed_posts p ON p.raw_post_id = r.id
            WHERE p.id IS NULL
            ORDER BY r.created_at ASC
            LIMIT %s
            """,
            (batch_size,),
        ).fetchall()
    return [RawPost(*row) for row in rows]


def upsert_processed_post(
    raw_post_id: UUID,
    dedup_cluster_id: UUID,
    sentiment_score: float,
    sentiment_method: str,
    topicality_score: float,
    is_dedup_canonical: bool = True,
    is_bot: bool = False,
    bot_score: float | None = None,
    entities: list | None = None,
    base_score: float | None = None,
    rank_score: float | None = None,
) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO processed_posts (
                raw_post_id, dedup_cluster_id, is_dedup_canonical, is_bot, bot_score,
                sentiment_score, sentiment_method, topicality_score, entities,
                base_score, rank_score
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (raw_post_id) DO UPDATE SET
                dedup_cluster_id   = EXCLUDED.dedup_cluster_id,
                is_dedup_canonical = EXCLUDED.is_dedup_canonical,
                is_bot             = EXCLUDED.is_bot,
                bot_score          = EXCLUDED.bot_score,
                sentiment_score    = EXCLUDED.sentiment_score,
                sentiment_method   = EXCLUDED.sentiment_method,
                topicality_score   = EXCLUDED.topicality_score,
                entities           = EXCLUDED.entities,
                base_score         = EXCLUDED.base_score,
                rank_score         = EXCLUDED.rank_score,
                processed_at       = NOW()
            """,
            (
                raw_post_id,
                dedup_cluster_id,
                is_dedup_canonical,
                is_bot,
                bot_score,
                sentiment_score,
                sentiment_method,
                topicality_score,
                Jsonb(entities) if entities is not None else None,
                base_score,
                rank_score,
            ),
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


def fetch_rankable_posts(since: datetime) -> list[RankableRow]:
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.text, r.created_at, p.sentiment_score, p.topicality_score,
                   p.entities, p.is_bot, p.is_dedup_canonical
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


def close() -> None:
    pool.close()
