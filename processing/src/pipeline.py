import logging
from datetime import datetime, timedelta, timezone

import bot_filter
import db
import dedup
import ranking
import sentiment
import topicality

logger = logging.getLogger("processing")

# Alpha-stage cap on stored data, not a correctness requirement -- raise
# post-alpha if needed. Note this makes ranking.MMR_WINDOW_HOURS (72h)
# effectively capped at this value too, since a post older than
# RETENTION_HOURS is deleted before it could ever be 72h old.
RETENTION_HOURS = 24


def run_cycle(batch_size: int) -> int:
    """Fetches a batch of unprocessed posts and scores them through dedup,
    bot filter, topicality, and sentiment, computing base_score (positivity
    x topicality x recency) per post directly. rank_score is left for
    refresh_rankings — MMR needs the full eligible pool, not just this
    batch."""
    posts = db.fetch_unprocessed_posts(batch_size)
    if not posts:
        return 0

    dedup_index = dedup.RedisDedupIndex()
    dedup_results = dedup.dedup_posts(posts, dedup_index)

    bot_index = bot_filter.RedisBotFilterIndex()
    burst_index = topicality.RedisBurstIndex()
    topicality_results = topicality.score_topicality(posts, burst_index)

    now = datetime.now(timezone.utc)

    for post in posts:
        cluster = dedup_results[post.id]
        bot_score = bot_filter.score_bot(post.author_id, post.text, cluster.cluster_id, bot_index)
        topic = topicality_results[post.id]
        sentiment_score = sentiment.score_sentiment(post.text)

        rankable = ranking.RankablePost(
            id=post.id,
            text=post.text,
            created_at=post.created_at,
            sentiment_score=sentiment_score,
            topicality_score=topic.score,
            entities=topic.entities,
            is_bot=bot_score.is_bot,
            is_dedup_canonical=cluster.is_canonical,
        )
        base_score = ranking.compute_base_score(rankable, now)

        db.upsert_processed_post(
            raw_post_id=post.id,
            dedup_cluster_id=cluster.cluster_id,
            sentiment_score=sentiment_score,
            sentiment_method=sentiment.SENTIMENT_METHOD,
            topicality_score=topic.score,
            is_dedup_canonical=cluster.is_canonical,
            is_bot=bot_score.is_bot,
            bot_score=bot_score.bot_score,
            entities=topic.entities,
            base_score=base_score,
            rank_score=None,
        )

    logger.info("processed %d posts", len(posts))
    return len(posts)


def refresh_rankings() -> int:
    """Re-runs MMR over the current eligible window. Needed even on cycles
    with no new posts — the window's membership shifts as posts age out,
    which changes MMR's diversity trade-offs for everyone still in it."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ranking.MMR_WINDOW_HOURS)
    rows = db.fetch_rankable_posts(cutoff)

    posts = [
        ranking.RankablePost(
            id=row.raw_post_id,
            text=row.text,
            created_at=row.created_at,
            sentiment_score=row.sentiment_score,
            topicality_score=row.topicality_score,
            entities=row.entities or [],
            is_bot=row.is_bot,
            is_dedup_canonical=row.is_dedup_canonical,
        )
        for row in rows
    ]

    results = ranking.rank_posts(posts)
    updates = [(post_id, result.base_score, result.rank_score) for post_id, result in results.items()]
    db.update_rank_scores(updates)

    logger.info("refreshed rankings for %d posts", len(results))
    return len(results)


def cleanup_old_data() -> int:
    """Deletes raw_posts older than RETENTION_HOURS; processed_posts rows
    for them cascade-delete automatically. Safe to run every cycle -- the
    delete is indexed (raw_posts_created_at_idx) and typically matches
    nothing once the initial backlog is cleared."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)
    deleted = db.delete_old_raw_posts(cutoff)
    if deleted:
        logger.info("cleaned up %d posts older than %dh", deleted, RETENTION_HOURS)
    return deleted
