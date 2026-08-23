import logging
import os
from datetime import datetime, timedelta, timezone

import config
from infra import db, redis_guard
from pipeline_stages import (
    bot_filter,
    category_model,
    content_filter,
    context_dependency,
    dedup,
    language_filter,
    moderation_recheck,
    quote_resolver,
    ranking,
    sentiment,
    thumbnail_resolver,
    topicality,
)

logger = logging.getLogger("processing")

# Alpha-stage cap, not a correctness requirement. See CLAUDE.md's Data
# retention section -- includes why ranking.RANKING_MMR_WINDOW_HOURS (72h)
# is left looking inconsistent with this on purpose.
RETENTION_HOURS = int(os.environ.get("RETENTION_HOURS", "24"))

# dedup's Redis state must outlive the posts it covers, or a still-live
# post can silently lose its dedup eligibility before it's actually
# deleted -- see the wiki's Deduplication page. Checked at startup, not
# left as a convention to remember.
if dedup.DEDUP_BAND_TTL_SECONDS < RETENTION_HOURS * 3600:
    raise ValueError(
        f"DEDUP_BAND_TTL_SECONDS ({dedup.DEDUP_BAND_TTL_SECONDS}) must be at least "
        f"RETENTION_HOURS in seconds ({RETENTION_HOURS * 3600})"
    )

# Bump when a change to any scoring stage (dedup/bot/topicality/sentiment/
# ranking) would make two posts' base_score/rank_score not directly
# comparable. See CLAUDE.md's Versioning & migration section. Deliberately
# not an env var -- it has to match what the deployed code actually does,
# not be independently set per environment.
PIPELINE_VERSION = "v3"

# Batch size for recheck_moderation()'s sweep -- see the wiki's
# Configuration page.
MODERATION_RECHECK_BATCH_SIZE = int(os.environ.get("MODERATION_RECHECK_BATCH_SIZE", "500"))


def enforce_redis_capacity() -> None:
    """Proactive Redis size guard -- call before run_cycle so this cycle's
    dedup/bot-filter/topicality writes happen with headroom already
    reclaimed, rather than discovering the cap mid-write. See the wiki's
    Configuration page."""
    redis_guard.enforce(config.REDIS_MAX_BYTES, config.REDIS_SOFT_LIMIT_RATIO)


def run_cycle(batch_size: int) -> int:
    """Fetches a batch of unprocessed posts and scores them through dedup,
    bot filter, topicality, and sentiment, computing base_score (positivity
    x topicality x recency) per post directly. rank_score is left for
    refresh_rankings — MMR needs the full eligible pool, not just this
    batch. See the wiki's Pipeline Internals page for the full per-stage
    walkthrough."""
    posts = db.fetch_unprocessed_posts(batch_size)
    if not posts:
        return 0

    # Four hard-exclude checks below, cheapest/most-likely-to-match first,
    # so a post is never scored once it's excluded. See the wiki's Content
    # Policy page for the policy behind each, and Pipeline Internals for
    # why this specific order.
    blocked = db.fetch_blocked_authors()
    suppressed_terms = db.fetch_suppressed_terms()
    suppressed_domains = db.fetch_suppressed_domains()

    context_classifications: dict = {}

    kept_posts = []
    for post in posts:
        if (post.source, post.author_id) in blocked:
            db.delete_raw_post(post.id)
            logger.info("moderation-blocked post %s (author %s/%s)", post.id, post.source, post.author_id)
        elif content_filter.is_content_excluded(
            post.source, post.text, post.raw_json, suppressed_terms, suppressed_domains
        ):
            db.delete_raw_post(post.id)
            logger.info(
                "content-filtered post %s (hashtag/self-label/spoiler-text/domain/sensitive-media/home-instance)",
                post.id,
            )
        elif (post.lang is None or post.source == "mastodon") and language_filter.is_non_english(post.text):
            db.delete_raw_post(post.id)
            reason = "no tag" if post.lang is None else f"tagged {post.lang!r}"
            logger.info("language-filtered post %s (%s, detected non-English)", post.id, reason)
        else:
            classification = context_dependency.classify(post.source, post.author_id, post.raw_json, post.text)
            if classification.action == "exclude":
                db.delete_raw_post(post.id)
                logger.info("context-dependency-excluded post %s (%s)", post.id, post.source)
            else:
                context_classifications[post.id] = classification
                kept_posts.append(post)

    if not kept_posts:
        logger.info("processed 0 posts (%d content-filtered)", len(posts))
        return len(posts)

    dedup_index = dedup.RedisDedupIndex()
    dedup_results = dedup.dedup_posts(kept_posts, dedup_index)

    bot_index = bot_filter.RedisBotFilterIndex()
    burst_index = topicality.RedisBurstIndex()
    topicality_results = topicality.score_topicality(kept_posts, burst_index)

    # One ONNX call for the whole batch, not one per post -- see the wiki's
    # Categorization page.
    category_results = category_model.categorize_batch(kept_posts, topicality_results)

    # Same batched shape as category_results above -- see the wiki's
    # Pipeline Internals page.
    sentiment_results = sentiment.score_sentiment_batch(kept_posts)

    # Batched/deduped resolve, not one call per post -- see the wiki's
    # Pipeline Internals page.
    quote_uris_by_post = {post.id: quote_resolver.extract_quote_uri(post.raw_json) for post in kept_posts}
    quote_content_by_uri = quote_resolver.resolve_quotes(
        [uri for uri in quote_uris_by_post.values() if uri is not None],
        suppressed_terms,
        suppressed_domains,
    )

    # Same batched/deduped shape as quote resolution above.
    thumbnail_urls_by_post = {
        post.id: thumbnail_resolver.extract_link_needing_thumbnail(post.source, post.raw_json, post.text)
        for post in kept_posts
    }
    thumbnail_by_url = thumbnail_resolver.resolve_thumbnails(
        [url for url in thumbnail_urls_by_post.values() if url is not None]
    )

    now = datetime.now(timezone.utc)

    upserts: list[db.ProcessedPostUpsert] = []
    for post in kept_posts:
        cluster = dedup_results[post.id]
        bot_score = bot_filter.score_bot(post.author_id, post.text, cluster.cluster_id, bot_index)
        topic = topicality_results[post.id]
        sentiment_score = sentiment_results[post.id]

        context_penalty = context_classifications[post.id].devalue_multiplier

        rankable = ranking.RankablePost(
            id=post.id,
            text=post.text,
            created_at=post.created_at,
            sentiment_score=sentiment_score,
            topicality_score=topic.score,
            entities=topic.entities,
            is_bot=bot_score.is_bot,
            is_dedup_canonical=cluster.is_canonical,
            context_penalty=context_penalty,
        )
        base_score = ranking.compute_base_score(rankable, now)

        # Deliberately not threaded into RankablePost/ranking.py -- see
        # CLAUDE.md's Category taxonomy section.
        category = category_results[post.id]

        quote_uri = quote_uris_by_post.get(post.id)
        quote_content = quote_content_by_uri.get(quote_uri) if quote_uri else None

        thumbnail_url = thumbnail_urls_by_post.get(post.id)
        generated_thumbnail_url = thumbnail_by_url.get(thumbnail_url) if thumbnail_url else None

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
                category_method=category_model.CATEGORY_METHOD,
                context_penalty=context_penalty,
                generated_thumbnail_url=generated_thumbnail_url,
            )
        )

    db.upsert_processed_posts(upserts)

    filtered_count = len(posts) - len(kept_posts)
    if filtered_count:
        logger.info("processed %d posts (%d content-filtered)", len(kept_posts), filtered_count)
    else:
        logger.info("processed %d posts", len(kept_posts))
    # Pre-filter count, not len(kept_posts) -- see the wiki's Pipeline
    # Internals page for why.
    return len(posts)


def refresh_rankings() -> int:
    """Re-runs MMR over the current eligible window. Needed even on cycles
    with no new posts — the window's membership shifts as posts age out,
    which changes MMR's diversity trade-offs for everyone still in it. See
    the wiki's Pipeline Internals and Configuration pages."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ranking.RANKING_MMR_WINDOW_HOURS)
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
            context_penalty=row.context_penalty,
        )
        for row in rows
    ]

    results = ranking.rank_posts(posts)
    updates = [(post_id, result.base_score, result.rank_score) for post_id, result in results.items()]
    db.update_rank_scores(updates)

    logger.info("refreshed rankings for %d posts", len(results))
    return len(results)


def purge_blocked_authors() -> int:
    """Retroactive half of the moderation blocklist -- run_cycle's check only
    stops *future* posts from a blocklisted author; this deletes any of
    their posts already sitting in raw_posts (processed_posts cascades), so
    a block takes effect on already-ingested posts within one cycle rather
    than waiting for retention to age them out. See the wiki's Content
    Policy and Pipeline Internals pages."""
    purged = db.purge_blocked_authors()
    if purged:
        logger.info("purged %d posts from newly/still-blocked authors", purged)
    return purged


def recheck_moderation() -> int:
    """Backstop against ingestion/'s blueskyLabels.ts real-time label-
    stream listener racing Jetstream's own insert for the same post (issue
    #67) -- independently re-verifies each already-scored Bluesky post's
    own moderation labels *and* its author's profile self-label against
    Bluesky's public AppView, mirroring quote_resolver.py's exact getPosts
    pattern. Purges (db.delete_raw_post, cascades to processed_posts) any
    match; marks every successfully-checked post either way via
    moderation_checked_at so a genuinely clean post is never re-swept.
    Throttled by the caller (main.py), unlike purge_blocked_authors --
    this one calls an external API, so it must not compound under backlog
    the way an unthrottled per-iteration DB-only sweep safely can. See the
    wiki's Content Policy and Pipeline Internals pages."""
    posts = db.fetch_unchecked_bluesky_posts(MODERATION_RECHECK_BATCH_SIZE)
    if not posts:
        return 0

    results = moderation_recheck.check_posts(posts)
    purged = 0
    checked_ids = []
    for post in posts:
        result = results.get(post.raw_post_id)
        if result is None:
            continue  # batch failed -- left unchecked, retried next sweep
        if result == "excluded":
            db.delete_raw_post(post.raw_post_id)
            purged += 1
            logger.info("moderation-recheck purged post %s (label backstop)", post.raw_post_id)
        else:
            checked_ids.append(post.raw_post_id)

    db.mark_moderation_checked(checked_ids)
    if purged:
        logger.info("moderation-recheck purged %d posts", purged)
    return purged


def cleanup_old_data() -> int:
    """Deletes raw_posts older than RETENTION_HOURS; processed_posts rows
    for them cascade-delete automatically. Safe to run every cycle -- the
    delete is indexed (raw_posts_created_at_idx) and typically matches
    nothing once the initial backlog is cleared. See CLAUDE.md's Data
    retention section."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)
    deleted = db.delete_old_raw_posts(cutoff)
    if deleted:
        logger.info("cleaned up %d posts older than %dh", deleted, RETENTION_HOURS)
    return deleted
