import gzip
import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import config
from infra import corpus_store, db, redis_guard
from pipeline_stages import (
    author_resolver,
    bot_filter,
    category_model,
    content_filter,
    context_dependency,
    corpus_export,
    dedup,
    existence_recheck,
    language_filter,
    mastodon_resolver,
    moderation_recheck,
    penalties,
    political_centroid,
    political_exclude,
    political_model,
    quality_exclude,
    quality_model,
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
PIPELINE_VERSION = "v19"

# Batch size for recheck_moderation()'s sweep -- see the wiki's
# Configuration page.
MODERATION_RECHECK_BATCH_SIZE = int(os.environ.get("MODERATION_RECHECK_BATCH_SIZE", "500"))

# Batch size for resolve_context()'s sweep -- see the wiki's Configuration
# page.
CONTEXT_RESOLVE_BATCH_SIZE = int(os.environ.get("CONTEXT_RESOLVE_BATCH_SIZE", "500"))

# Batch size for resolve_authors()'s sweep -- see the wiki's Configuration
# page.
AUTHOR_RESOLVE_BATCH_SIZE = int(os.environ.get("AUTHOR_RESOLVE_BATCH_SIZE", "500"))

# Batch size for recheck_existence()'s sweep -- see the wiki's Configuration
# page.
EXISTENCE_RECHECK_BATCH_SIZE = int(os.environ.get("EXISTENCE_RECHECK_BATCH_SIZE", "500"))

# Corpus export -- see the wiki's Configuration page and Processing
# Infrastructure's "Corpus export" section. Sized for headroom over the
# per-cycle inflow now that near-duplicates are kept too (~1.4x the
# canonical-only rate).
EXPORT_CORPUS_BATCH_SIZE = int(os.environ.get("EXPORT_CORPUS_BATCH_SIZE", "3000"))
# How long a scored post is held back from the archive so every
# retroactive-exclusion path has fired first. Well inside RETENTION_HOURS.
EXPORT_CORPUS_MIN_AGE_HOURS = int(os.environ.get("EXPORT_CORPUS_MIN_AGE_HOURS", "6"))
# Key prefix inside the goodgorithm-corpus bucket; `raw/` and `shards/`
# live under it.
CORPUS_R2_PREFIX = os.environ.get("CORPUS_R2_PREFIX", "corpus")


def enforce_redis_capacity() -> None:
    """Proactive Redis size guard -- call before run_cycle so this cycle's
    dedup/bot-filter/topicality writes happen with headroom already
    reclaimed, rather than discovering the cap mid-write. See the wiki's
    Configuration page."""
    redis_guard.enforce(config.REDIS_MAX_BYTES, config.REDIS_SOFT_LIMIT_RATIO)


def run_cycle(batch_size: int) -> int:
    """Fetches a batch of unprocessed posts and scores them through political/
    quality screening, dedup, bot filter, topicality, category, and sentiment,
    computing base_score (quality_score x recency) per post directly.
    rank_score is left for refresh_rankings — MMR needs the full eligible
    pool, not just this batch. See the wiki's Pipeline Internals page for
    the full per-stage walkthrough."""
    posts = db.fetch_unprocessed_posts(batch_size)
    if not posts:
        return 0

    # Three hard-exclude checks below, cheapest/most-likely-to-match first,
    # so a post is never scored once it's excluded. See the wiki's Content
    # Policy page for the policy behind each, and Pipeline Internals for
    # why this specific order.
    mod = db.fetch_moderation_lists()

    context_classifications: dict = {}

    kept_posts = []
    for post in posts:
        if content_filter.is_content_excluded(
            post.source, post.text, post.raw_json, mod.suppressed_terms, mod.suppressed_domains
        ):
            db.delete_raw_post(post.id)
            logger.info(
                "content-filtered post %s (hashtag/bluesky-funnel/self-label/spoiler-text/domain/sensitive-media/home-instance)",
                post.id,
            )
        elif (
            post.lang is None
            or post.source == "mastodon"
            or (post.source == "bluesky" and language_filter.bluesky_tag_needs_recheck(post.lang, post.text))
        ) and language_filter.is_non_english(post.text):
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

    # Political scoring + the AND-gate hard-exclude, right after the cheap
    # filter loop and before dedup/bot/topicality/sentiment/category all
    # run -- an excluded post shouldn't waste any of that compute. Computed
    # once here; political_results is reused below for the devalue penalty
    # (the centroid score only matters for this exclude decision).
    political_results = political_model.score_batch(kept_posts)
    political_centroid_results = political_centroid.score_batch(kept_posts)

    survivors = []
    for post in kept_posts:
        classifier_score = political_results.get(post.id)
        centroid_score = political_centroid_results.get(post.id)
        if political_exclude.is_political_excluded(classifier_score, centroid_score):
            db.delete_raw_post(post.id)
            logger.info(
                "political-excluded post %s (classifier=%.3f centroid=%.3f)",
                post.id,
                classifier_score,
                centroid_score,
            )
        else:
            survivors.append(post)
    kept_posts = survivors

    if not kept_posts:
        logger.info("processed 0 posts (%d content/political-filtered)", len(posts))
        return len(posts)

    # Quality scoring + hard-exclude at the decided threshold (0.39), same
    # "before dedup/bot/topicality/sentiment/category" placement and
    # compute-saving reasoning as the political block above. Single-signal,
    # unlike political's AND-gate -- see quality_exclude.py's own docstring
    # for why.
    quality_results = quality_model.score_batch(kept_posts)

    survivors = []
    for post in kept_posts:
        quality_score = quality_results.get(post.id)
        if quality_exclude.is_quality_excluded(quality_score):
            db.delete_raw_post(post.id)
            logger.info("quality-excluded post %s (score=%.3f)", post.id, quality_score)
        else:
            survivors.append(post)
    kept_posts = survivors

    if not kept_posts:
        logger.info("processed 0 posts (%d content/political/quality-filtered)", len(posts))
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
    # Sentiment page.
    sentiment_results = sentiment.score_sentiment_batch(kept_posts)

    # Same batched/deduped shape as quote/reply-context resolution --
    # resolve_context() runs on its own throttled sweep instead (see
    # resolve_context() below), not inline here.
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
        bot_score = bot_filter.score_bot(
            post.source, post.author_id, post.text, cluster.cluster_id, bot_index, mod.post_shape_config
        )
        topic = topicality_results[post.id]
        sentiment_score = sentiment_results[post.id]

        political_score = political_results.get(post.id)

        # A "pending" post (Bluesky reply/quote awaiting resolve_context())
        # never gets a quality_score/base_score on this pass, deliberately
        # pessimistic: it doesn't rank on its own merit alone until we also
        # know its referenced content isn't itself excluded. Already-computed
        # quality_results[post.id] is discarded here for a pending post --
        # resolve_context() recomputes it fresh once resolution completes,
        # combined with the resolved target's own score. compute_base_score
        # already returns 0.0 for quality_score=None (the model-outage
        # fail-open path), so this needs no new ranking.py logic.
        context_classification = context_classifications[post.id]
        is_pending = context_classification.action == "pending"
        quality_score = None if is_pending else quality_results.get(post.id)

        penalty = penalties.apply(
            penalties.PenaltyContext(
                source=post.source,
                author_id=post.author_id,
                aggregator_instances=mod.aggregator_instances,
            )
        )

        rankable = ranking.RankablePost(
            id=post.id,
            text=post.text,
            created_at=post.created_at,
            quality_score=quality_score,
            entities=topic.entities,
            is_bot=bot_score.is_bot,
            is_dedup_canonical=cluster.is_canonical,
            source=post.source,
            author_id=post.author_id,
        )
        base_score = ranking.compute_base_score(rankable, now)

        # Deliberately not threaded into RankablePost/ranking.py -- see
        # CLAUDE.md's Category taxonomy section.
        category = category_results[post.id]

        thumbnail_url = thumbnail_urls_by_post.get(post.id)
        generated_thumbnail_url = thumbnail_by_url.get(thumbnail_url) if thumbnail_url else None

        upserts.append(
            db.ProcessedPostUpsert(
                raw_post_id=post.id,
                source=post.source,
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
                category=category,
                category_method=category_model.CATEGORY_METHOD,
                penalty_multiplier=penalty.multiplier,
                penalty_detail=penalty.detail,
                generated_thumbnail_url=generated_thumbnail_url,
                political_score=political_score,
                political_method=political_model.POLITICAL_METHOD if political_score is not None else None,
                quality_score=quality_score,
                quality_method=None if is_pending else (quality_model.QUALITY_METHOD if quality_score is not None else None),
                context_status="pending" if is_pending else None,
                context_kind=context_classification.context_kind,
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
    rows = db.fetch_rankable_posts(cutoff, ranking.RANKING_MMR_CANDIDATE_POOL_SIZE)

    posts = [
        ranking.RankablePost(
            id=row.raw_post_id,
            text=row.text,
            created_at=row.created_at,
            quality_score=row.quality_score,
            entities=row.entities or [],
            is_bot=row.is_bot,
            is_dedup_canonical=row.is_dedup_canonical,
            source=row.source,
            author_id=row.author_id,
        )
        for row in rows
    ]

    results = ranking.rank_posts(posts)
    updates = [(post_id, result.base_score, result.rank_score) for post_id, result in results.items()]
    db.update_rank_scores(updates)

    logger.info("refreshed rankings for %d posts", len(results))
    return len(results)


def resolve_authors() -> int:
    """Resolves a post's own author display name/avatar via Bluesky's
    public AppView -- Jetstream's firehose never carries this, unlike
    Mastodon whose API response embeds it for free (api/ reads it straight
    from raw_json for those, no resolution needed). Deliberately scoped to
    already-*ranked* posts only (db.fetch_bluesky_posts_needing_author_resolution),
    not every ingested post -- only a small fraction of ingested Bluesky
    posts ever get ranked/shown at all, so resolving the rest would be
    pure waste. Must run after refresh_rankings() in the caller's loop, not before --
    its candidate population depends on rank_score already being set this
    cycle. Throttled by the caller (main.py), same reasoning as
    recheck_moderation -- this calls an external API in batches, must not
    compound under a large backlog. See the wiki's Bluesky AppView
    Resolvers and Configuration pages."""
    posts = db.fetch_bluesky_posts_needing_author_resolution(AUTHOR_RESOLVE_BATCH_SIZE)
    if not posts:
        return 0

    results = author_resolver.resolve_authors(posts)
    resolved: list[tuple] = []
    for post in posts:
        if post.raw_post_id not in results:
            continue  # batch failed -- left unresolved, retried next sweep
        resolved.append((post.raw_post_id, results[post.raw_post_id]))

    db.mark_authors_resolved(resolved)
    found = sum(1 for _, author in resolved if author is not None)
    if resolved:
        logger.info("resolved author info for %d/%d swept bluesky posts", found, len(resolved))
    return found


def purge_blocked_authors() -> int:
    """Retroactive half of the moderation blocklist -- run_cycle's check only
    stops *future* posts from a blocklisted author; this deletes any of
    their posts already sitting in raw_posts (processed_posts cascades), so
    a block takes effect on already-ingested posts within its own throttle
    window (main.py's PURGE_BLOCKED_AUTHORS_INTERVAL_SECONDS) rather than
    waiting for retention to age them out. See the wiki's Content Policy
    and Pipeline Internals pages."""
    purged = db.purge_blocked_authors()
    if purged:
        logger.info("purged %d posts from newly/still-blocked authors", purged)
    return purged


def recheck_moderation() -> int:
    """Backstop against ingestion/'s blueskyLabels.ts real-time label-
    stream listener racing Jetstream's own insert for the same post --
    independently re-verifies each already-scored Bluesky post's
    own moderation labels *and* its author's profile self-label against
    Bluesky's public AppView, mirroring quote_resolver.py's exact getPosts
    pattern. Purges (db.delete_raw_post, cascades to processed_posts) any
    match; marks every successfully-checked post either way via
    moderation_checked_at so a genuinely clean post is never re-swept.
    Throttled by the caller (main.py), same as purge_blocked_authors, but
    for a different reason -- this one calls an external API, so it must
    not compound into a burst of calls under a large backlog, unlike a
    DB-only sweep. See the wiki's Content Policy and Pipeline Internals
    pages."""
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


@dataclass(frozen=True)
class _ScorableText:
    """A lightweight (id, text) pair -- reuses quality_model.score_batch()/
    political_model.score_batch()'s batched-ONNX-call shape for
    resolve_context()'s own ad-hoc scoring needs (a pending post's own
    text, and its resolved target's text) without needing a full RawPost."""

    id: UUID
    text: str


def resolve_context() -> int:
    """Resolves a batch of replies/quote-posts pending their target's
    content (see context_dependency.py, quote_resolver.py,
    mastodon_resolver.py). A separate sweep, not inline in run_cycle --
    reply volume is roughly half of Bluesky's stream, far more than
    resolving synchronously within run_cycle could absorb without hurting
    throughput. Throttled by the caller (main.py), same reasoning as
    recheck_moderation -- calls an external API in batches. See issue
    #292/#293 and the wiki's Pipeline Internals page.

    Dispatches each target to Bluesky's AppView or a Mastodon instance's
    status endpoint by the target's own shape (an at:// AT-URI vs an
    {instance}/{id} pair) -- a Mastodon post's quote-inline/RE: target is
    a *Bluesky* post, so source alone can't decide the resolver. See
    context_dependency.py's module docstring.

    A target that fails content-filtering/an adult label (either
    resolver's own "filtered" status), fails language_filter, fails
    political_exclude, or belongs to an author with a recent is_bot
    verdict of their own excludes the whole post -- not just a devalue,
    since this actually looks at what's being referenced. A target that
    resolves cleanly gets its own quality_score computed and combined via
    min() with the pending post's own quality_score -- a conservative
    floor, not a boost: a thread never scores better than its weaker
    half. A target that can't be resolved at all (not_found, or a failed
    batch/request) falls back to scoring the pending post standalone,
    marked context_status = 'unavailable' so a future UI pass can
    surface that it happened."""
    pending = db.fetch_context_pending(CONTEXT_RESOLVE_BATCH_SIZE)
    if not pending:
        return 0

    mod = db.fetch_moderation_lists()
    targets_by_post = {
        post.raw_post_id: context_dependency.classify(
            post.source, post.author_id, post.raw_json, post.text
        ).context_target
        for post in pending
    }
    all_targets = [t for t in targets_by_post.values() if t is not None]
    bluesky_targets = [t for t in all_targets if t.startswith("at://")]
    mastodon_targets = [t for t in all_targets if not t.startswith("at://")]

    bsky_content, bsky_author_ids = quote_resolver.resolve_context(
        bluesky_targets, mod.suppressed_terms, mod.suppressed_domains
    )
    masto_content, masto_author_ids = mastodon_resolver.resolve_context(
        mastodon_targets, mod.suppressed_terms, mod.suppressed_domains
    )
    content_by_target = {**bsky_content, **masto_content}
    author_id_by_target = {**bsky_author_ids, **masto_author_ids}

    # Batched, not per-post -- only for targets that actually resolved,
    # since there's nothing to political-check/quality-score otherwise.
    available_by_post: dict[UUID, dict] = {}
    for post in pending:
        target = targets_by_post.get(post.raw_post_id)
        content = content_by_target.get(target) if target is not None else None
        if content is not None and content.get("status") == "available":
            available_by_post[post.raw_post_id] = content

    target_texts = [_ScorableText(id=pid, text=c["text"]) for pid, c in available_by_post.items()]
    target_political = political_model.score_batch(target_texts)
    target_political_centroid = political_centroid.score_batch(target_texts)
    target_quality = quality_model.score_batch(target_texts)

    own_texts = [_ScorableText(id=post.raw_post_id, text=post.text) for post in pending]
    own_quality = quality_model.score_batch(own_texts)

    purged = 0
    resolutions: list[db.ContextResolution] = []
    for post in pending:
        content = available_by_post.get(post.raw_post_id)
        own_score = own_quality.get(post.raw_post_id)

        if content is None:
            target = targets_by_post.get(post.raw_post_id)
            resolved_but_unavailable = target is not None and content_by_target.get(target) is not None
            reason = content_by_target.get(target, {}).get("reason") if resolved_but_unavailable else "not_found"
            if reason == "filtered":
                db.delete_raw_post(post.raw_post_id)
                purged += 1
                logger.info("context-resolution-excluded post %s (target filtered)", post.raw_post_id)
            else:
                resolutions.append(
                    db.ContextResolution(
                        raw_post_id=post.raw_post_id,
                        quality_score=own_score,
                        quality_method=quality_model.QUALITY_METHOD if own_score is not None else None,
                        context_content=None,
                    )
                )
            continue

        target = targets_by_post[post.raw_post_id]

        if language_filter.is_non_english(content["text"]):
            db.delete_raw_post(post.raw_post_id)
            purged += 1
            logger.info("context-resolution-excluded post %s (target non-English)", post.raw_post_id)
            continue

        classifier_score = target_political.get(post.raw_post_id)
        centroid_score = target_political_centroid.get(post.raw_post_id)
        if political_exclude.is_political_excluded(classifier_score, centroid_score):
            db.delete_raw_post(post.raw_post_id)
            purged += 1
            logger.info("context-resolution-excluded post %s (target political)", post.raw_post_id)
            continue

        # The target's own platform, not post.source -- a Mastodon post's
        # quote-inline/RE: target is Bluesky content, so post.source alone
        # would give the wrong answer here for that case.
        target_source = "bluesky" if target.startswith("at://") else "mastodon"
        target_author_id = author_id_by_target.get(target)
        if target_author_id is not None and db.recent_bot_verdict(target_source, target_author_id):
            db.delete_raw_post(post.raw_post_id)
            purged += 1
            logger.info("context-resolution-excluded post %s (target author is_bot)", post.raw_post_id)
            continue

        target_score = target_quality.get(post.raw_post_id)
        if own_score is not None and target_score is not None:
            combined_score = min(own_score, target_score)
        else:
            combined_score = own_score if own_score is not None else target_score  # fail-open

        if combined_score is not None and quality_exclude.is_quality_excluded(combined_score):
            db.delete_raw_post(post.raw_post_id)
            purged += 1
            logger.info(
                "context-resolution-excluded post %s (combined score=%.3f)", post.raw_post_id, combined_score
            )
            continue

        resolutions.append(
            db.ContextResolution(
                raw_post_id=post.raw_post_id,
                quality_score=combined_score,
                quality_method=quality_model.QUALITY_METHOD if combined_score is not None else None,
                context_content=content,
            )
        )

    db.apply_context_resolution(resolutions)
    if purged:
        logger.info("context-resolution purged %d posts", purged)
    return purged


def recheck_existence(stale_hours: int) -> int:
    """Deletes an already-ranked Bluesky post (db.delete_raw_post, cascades
    to processed_posts) once it stops resolving on Bluesky's AppView --
    user delete, post detach, or the author's account being taken down /
    suspended / deleted. None of those emit a com.atproto.label event, so
    neither ingestion/'s label stream nor recheck_moderation catches them.

    Unlike recheck_moderation's one-shot moderation_checked_at, this is a
    *rolling* re-check: existence_checked_at is re-derived, so a row is
    re-swept once its last check is older than stale_hours, across its
    whole 24h feed life -- a takedown usually lands hours after ingestion.
    It also backstops ingestion/'s real-time Jetstream delete/account
    handling, whose cursorless connection loses frames across a reconnect.

    Throttled by the caller (main.py) for the same reason as
    recheck_moderation -- an external API call in batches must not compound
    under a large backlog. Must run after refresh_rankings() in the loop:
    its candidate set is rank_score IS NOT NULL. Deletion, not a score
    change, so PIPELINE_VERSION is unaffected."""
    posts = db.fetch_bluesky_posts_needing_existence_recheck(EXISTENCE_RECHECK_BATCH_SIZE, stale_hours)
    if not posts:
        return 0

    results = existence_recheck.check_existence(posts)
    gone = 0
    present_ids = []
    for post in posts:
        result = results.get(post.raw_post_id)
        if result is None:
            continue  # batch failed -- left unchecked, retried next sweep
        if result == "gone":
            db.delete_raw_post(post.raw_post_id)
            gone += 1
            logger.info("existence-recheck purged post %s (no longer on AppView)", post.raw_post_id)
        else:
            present_ids.append(post.raw_post_id)

    db.mark_existence_checked(present_ids)
    if gone:
        logger.info("existence-recheck purged %d posts", gone)
    return gone


def cleanup_old_data() -> int:
    """Deletes raw_posts older than RETENTION_HOURS; processed_posts rows
    for them cascade-delete automatically. Safe to run every cycle -- the
    delete is indexed (raw_posts_created_at_idx) and typically matches
    nothing once the initial backlog is cleared. db.delete_old_raw_posts
    chunks the delete and caps it at DB_CLEANUP_MAX_PER_CYCLE, so a real
    backlog behind the cutoff drains over several cycles rather than one
    oversized statement. See CLAUDE.md's Data retention section."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)
    deleted = db.delete_old_raw_posts(cutoff)
    if deleted:
        capped = " (capped -- more remain for the next cycle)" if deleted >= db.DB_CLEANUP_MAX_PER_CYCLE else ""
        logger.info("cleaned up %d posts older than %dh%s", deleted, RETENTION_HOURS, capped)
    return deleted


def export_corpus() -> int:
    """Appends moderation-final post text -- canonical and near-duplicate,
    each record carrying is_dedup_canonical -- to the long-lived
    goodgorithm-corpus R2 bucket before RETENTION_HOURS deletes the
    raw_posts row. Gated by the caller on config.CORPUS_EXPORT_ENABLED
    (off outside production) and config.corpus_r2_configured().

    Mirrors recheck_moderation's shape: fetch a bounded batch, do the work,
    mark done -- but the "done" mark (exported_at) is only written for rows
    whose R2 PUT actually succeeded, so a failed object is re-selected and
    retried next sweep. Runs after purge_blocked_authors in the loop so a
    same-cycle block has already removed its rows before this reads
    candidates; the monthly compaction pass is the backstop for a re-export
    inside the retry window or a post excluded after it was archived. See
    the wiki's Processing Infrastructure page."""
    posts = db.fetch_unexported_posts(EXPORT_CORPUS_BATCH_SIZE, EXPORT_CORPUS_MIN_AGE_HOURS)
    if not posts:
        return 0

    store = corpus_store.CorpusStore()
    exported_ids: list = []
    for obj in corpus_export.build_objects(CORPUS_R2_PREFIX, posts):
        try:
            store.put_bytes(obj.key, obj.data)
        except Exception:
            logger.exception("corpus export failed for %s -- retrying next sweep", obj.key)
            continue
        exported_ids.extend(obj.raw_post_ids)

    db.mark_exported(exported_ids)
    if exported_ids:
        logger.info("exported %d/%d swept posts to the corpus", len(exported_ids), len(posts))
    return len(exported_ids)


def compact_corpus() -> int:
    """For every complete month with `raw/` objects and no shard yet,
    stream its records, drop exact-text duplicates, and write a single
    `shards/YYYY-MM.ndjson.gz`. This is what makes the export sweep's
    exactly-once semantics a non-issue -- re-exports in the retry window,
    mid-batch restarts, a stray write, and the same text from two sources
    all collapse here. Does not delete `raw/` objects; a consumer reads
    `shards/` plus the current month's `raw/`.

    A completed month never gets new `raw/` objects (export only writes
    objects dated to a post's own processed_at, which is at most hours
    old), so a month that already has a shard is skipped. The caller runs
    this once per UTC day, so that skip is what keeps the daily check
    cheap -- a couple of list calls on every day except the one after a
    month rolls over.

    Deduplication holds a set of 16-byte text hashes for the month in
    memory (~0.5 GB at current volume) -- the scaling limit; a sort-based
    external dedup replaces it if corpus volume grows an order of
    magnitude. Gated by the caller, same as export_corpus. See the wiki's
    Processing Infrastructure page."""
    store = corpus_store.CorpusStore()
    raw_prefix = f"{CORPUS_R2_PREFIX}/raw/"
    shard_prefix = f"{CORPUS_R2_PREFIX}/shards/"
    keys_by_month: dict[str, list[str]] = {}
    for key in store.list_keys(raw_prefix):
        # <prefix>/raw/YYYY/MM/DD/<file>
        parts = key[len(raw_prefix) :].split("/")
        if len(parts) >= 3:
            keys_by_month.setdefault(f"{parts[0]}-{parts[1]}", []).append(key)

    existing_shards = {
        key[len(shard_prefix) :].removesuffix(".ndjson.gz") for key in store.list_keys(shard_prefix)
    }
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    compacted = 0
    for month, keys in sorted(keys_by_month.items()):
        if month >= current_month or month in existing_shards:
            continue  # still being written to, or already compacted
        seen: set[bytes] = set()
        kept = 0
        with tempfile.NamedTemporaryFile(suffix=".ndjson.gz") as tmp:
            with gzip.GzipFile(fileobj=tmp, mode="wb") as gz:
                for key in sorted(keys):
                    for record in corpus_export.iter_records(store.get_bytes(key)):
                        digest = hashlib.blake2b(
                            corpus_export.dedup_key(record).encode("utf-8"), digest_size=16
                        ).digest()
                        if digest in seen:
                            continue
                        seen.add(digest)
                        gz.write(
                            (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
                                "utf-8"
                            )
                        )
                        kept += 1
            tmp.seek(0)
            store.put_fileobj(f"{CORPUS_R2_PREFIX}/shards/{month}.ndjson.gz", tmp)
        logger.info("compacted corpus month %s: %d unique records", month, kept)
        compacted += 1
    return compacted
