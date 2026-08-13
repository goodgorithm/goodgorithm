import logging
from datetime import datetime, timedelta, timezone

import bot_filter
import config
import content_filter
import db
import dedup
import language_filter
import quote_resolver
import ranking
import redis_guard
import sentiment
import taxonomy
import topicality
from dedup import normalize_text

logger = logging.getLogger("processing")

# Alpha-stage cap on stored data, not a correctness requirement -- raise
# post-alpha if needed. Note this makes ranking.MMR_WINDOW_HOURS (72h)
# effectively capped at this value too, since a post older than
# RETENTION_HOURS is deleted before it could ever be 72h old.
RETENTION_HOURS = 24

# Which version of this pipeline's scoring logic (dedup/bot/topicality/
# sentiment/ranking, taken together) produced a post's scores -- mirrors how
# sentiment_method already records which sentiment scorer (CNN vs VADER)
# produced a score, at the whole-pipeline level rather than one stage.
# processed_posts.pipeline_version existed as a schema column (DEFAULT 'v1')
# since the table was created, 2026-08-08, but was never actually written by
# this module until now -- see CLAUDE.md's Versioning & migration section.
# Bump this when a change to any scoring stage would make two posts'
# base_score/rank_score not directly comparable to each other.
PIPELINE_VERSION = "v2"


def enforce_redis_capacity() -> None:
    """Proactive Redis size guard -- call before run_cycle so this cycle's
    dedup/bot-filter/topicality writes (the ones that actually crashed
    production on 2026-08-12) happen with headroom already reclaimed if
    needed, rather than discovering the cap mid-write."""
    redis_guard.enforce(config.REDIS_MAX_BYTES)


def run_cycle(batch_size: int) -> int:
    """Fetches a batch of unprocessed posts and scores them through dedup,
    bot filter, topicality, and sentiment, computing base_score (positivity
    x topicality x recency) per post directly. rank_score is left for
    refresh_rankings — MMR needs the full eligible pool, not just this
    batch."""
    posts = db.fetch_unprocessed_posts(batch_size)
    if not posts:
        return 0

    # Hard content-exclude runs before dedup/bot/topicality -- no point
    # spending Redis/CPU on content that's about to be deleted. Excluded
    # posts never get a processed_posts row at all. Moderation blocklist
    # (issue #7) is checked here too, same position/reasoning -- a known
    # bad actor's posts are excluded before they're ever scored, whether
    # the block came from a moderator's manual entry or the Bluesky
    # bot-label auto-insert (ingestion/src/blueskyLabels.ts).
    #
    # Language verification (issue #28) only runs when post.lang is None --
    # ingestion/'s own language filters (bluesky.ts/mastodon.ts) already
    # exclude anything self-/server-tagged as non-English; the confirmed
    # gap was specifically posts with no language signal at all
    # (~11-13% of ingested volume), which those filters let through
    # unconditionally on the assumption "no tag = English". A tagged post
    # has already been through that check, so re-verifying its content
    # here wouldn't change anything.
    blocked = db.fetch_blocked_authors()

    kept_posts = []
    for post in posts:
        if (post.source, post.author_id) in blocked:
            db.delete_raw_post(post.id)
            logger.info("moderation-blocked post %s (author %s/%s)", post.id, post.source, post.author_id)
        elif content_filter.is_content_excluded(post.text, post.raw_json):
            db.delete_raw_post(post.id)
            logger.info("content-filtered post %s (hashtag/self-label)", post.id)
        elif post.lang is None and language_filter.is_non_english(post.text):
            db.delete_raw_post(post.id)
            logger.info("language-filtered post %s (no tag, detected non-English)", post.id)
        else:
            kept_posts.append(post)

    if not kept_posts:
        logger.info("processed 0 posts (%d content-filtered)", len(posts))
        return len(posts)

    dedup_index = dedup.RedisDedupIndex()
    dedup_results = dedup.dedup_posts(kept_posts, dedup_index)

    bot_index = bot_filter.RedisBotFilterIndex()
    burst_index = topicality.RedisBurstIndex()
    topicality_results = topicality.score_topicality(kept_posts, burst_index)

    # One batched resolve call per cycle rather than one per post -
    # extract_quote_uri returns None for the vast majority of posts (no
    # quote embed), so this is typically a handful of AppView requests per
    # cycle, not hundreds.
    quote_uris_by_post = {post.id: quote_resolver.extract_quote_uri(post.raw_json) for post in kept_posts}
    quote_content_by_uri = quote_resolver.resolve_quotes(
        [uri for uri in quote_uris_by_post.values() if uri is not None]
    )

    now = datetime.now(timezone.utc)

    upserts: list[db.ProcessedPostUpsert] = []
    for post in kept_posts:
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

        # Deliberately not threaded into RankablePost/ranking.py -- category
        # is a post-hoc filter on the existing rank_score, not a ranking
        # input. See taxonomy.py for the matching rules.
        category = taxonomy.categorize(topic.entities, topic.top_terms, normalize_text(post.text))

        quote_uri = quote_uris_by_post.get(post.id)
        quote_content = quote_content_by_uri.get(quote_uri) if quote_uri else None

        upserts.append(
            db.ProcessedPostUpsert(
                raw_post_id=post.id,
                dedup_cluster_id=cluster.cluster_id,
                sentiment_score=sentiment_score,
                sentiment_method=sentiment.SENTIMENT_METHOD,
                topicality_score=topic.score,
                pipeline_version=PIPELINE_VERSION,
                is_dedup_canonical=cluster.is_canonical,
                is_bot=bot_score.is_bot,
                bot_score=bot_score.bot_score,
                entities=topic.entities,
                base_score=base_score,
                rank_score=None,
                quote_content=quote_content,
                category=category,
            )
        )

    db.upsert_processed_posts(upserts)

    filtered_count = len(posts) - len(kept_posts)
    if filtered_count:
        logger.info("processed %d posts (%d content-filtered)", len(kept_posts), filtered_count)
    else:
        logger.info("processed %d posts", len(kept_posts))
    # Pre-filter count, not len(kept_posts) -- main.py's backlog-aware sleep
    # needs "did this cycle do work", and a cycle that filters everything
    # and keeps nothing should still count as work, not idle.
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


def purge_blocked_authors() -> int:
    """Retroactive half of the moderation blocklist (issue #7) -- run_cycle's
    check only stops *future* posts from a blocklisted author; this deletes
    any of their posts already sitting in raw_posts (processed_posts
    cascades), so a moderator's manual entry or the Bluesky bot-label
    auto-insert takes effect on already-ingested/already-ranked posts too,
    within one processing cycle rather than waiting for retention to age
    them out."""
    purged = db.purge_blocked_authors()
    if purged:
        logger.info("purged %d posts from newly/still-blocked authors", purged)
    return purged


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
