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


def close() -> None:
    pool.close()
