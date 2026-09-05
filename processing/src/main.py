import argparse
import logging
import os
import signal
import time
from datetime import datetime, timezone

import config
import pipeline
from infra import db, degradation, heartbeat, network_detector, status_server

logging.basicConfig(level=logging.INFO, format="[processing] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("processing")

_shutdown = False


def _handle_sigterm(signum, frame) -> None:
    global _shutdown
    logger.info("shutting down")
    _shutdown = True


def _daily_task_due(now_utc: datetime, hour_utc: int, last_run_date) -> bool:
    """True once per UTC day, on the first check at or after hour_utc that
    day. last_run_date is None on process start, so the first check past
    the hour after a restart runs -- an elapsed-seconds interval can't do
    that."""
    return now_utc.hour >= hour_utc and now_utc.date() != last_run_date


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument(
        "--batch-size", type=int, default=int(os.environ.get("PROCESSING_BATCH_SIZE", 500))
    )
    parser.add_argument(
        "--interval", type=int, default=int(os.environ.get("PROCESSING_INTERVAL_SECONDS", 300))
    )
    # Only taken as idle time when a cycle had nothing to process -- under a
    # real backlog, cycles run back-to-back on this shorter buffer instead.
    # See the wiki's Configuration page.
    parser.add_argument(
        "--backlog-buffer",
        type=int,
        default=int(os.environ.get("PROCESSING_BACKLOG_BUFFER_SECONDS", 3)),
    )
    # Throttled well below cycle frequency -- refresh_rankings() rebuilds
    # MMR's similarity matrices from scratch, real O(n^2) work. See the
    # wiki's Configuration page.
    parser.add_argument(
        "--refresh-interval",
        type=int,
        default=int(os.environ.get("REFRESH_RANKINGS_INTERVAL_SECONDS", 30)),
    )
    # A full-table aggregate looking for a slow-forming pattern, not
    # near-real-time freshness -- throttled far less frequently than
    # --refresh-interval above. See the wiki's Configuration page.
    parser.add_argument(
        "--network-detection-interval",
        type=int,
        default=int(os.environ.get("NETWORK_DETECTION_INTERVAL_SECONDS", 3600)),
    )
    # Redis usage can't spike meaningfully within a few seconds, so this
    # doesn't need checking on every single loop iteration -- throttled
    # the same way as --refresh-interval. See the wiki's Configuration page.
    parser.add_argument(
        "--redis-guard-interval",
        type=int,
        default=int(os.environ.get("REDIS_GUARD_INTERVAL_SECONDS", 30)),
    )
    # Also throttled, like --purge-blocked-authors-interval below, but for
    # a different reason: this calls an external API in batches, so a
    # large backlog must not be able to turn it into a burst of calls to
    # Bluesky's AppView. Still comfortably beats --refresh-interval's 30s
    # floor, which is what actually gates a post becoming feed-visible.
    # See the wiki's Configuration page.
    parser.add_argument(
        "--moderation-recheck-interval",
        type=int,
        default=int(os.environ.get("MODERATION_RECHECK_INTERVAL_SECONDS", 10)),
    )
    # A cheap, well-indexed DB-only join (see the wiki's Pipeline Internals
    # page) -- throttled anyway, since blocklist entries are rare and this
    # only governs how quickly a newly-blocked author's already-ingested
    # backlog gets swept, where a short delay is a non-issue. Their *future*
    # posts are already kept out of raw_posts by ingestion/'s own pre-insert
    # skip (bounded by its MODERATION_LISTS_REFRESH_SECONDS cache).
    parser.add_argument(
        "--purge-blocked-authors-interval",
        type=int,
        default=int(os.environ.get("PURGE_BLOCKED_AUTHORS_INTERVAL_SECONDS", 60)),
    )
    # Cosmetic, not a safety backstop like --moderation-recheck-interval --
    # no need to chase Bluesky's AppView aggressively for this. Must run
    # after refresh_rankings in the loop below: its candidate population
    # (rank_score IS NOT NULL) depends on that stage having already run
    # this cycle. See the wiki's Configuration page.
    parser.add_argument(
        "--author-resolve-interval",
        type=int,
        default=int(os.environ.get("AUTHOR_RESOLVE_INTERVAL_SECONDS", 60)),
    )
    # Corpus export sweep -- appends feed-eligible post text to the
    # goodgorithm-corpus R2 bucket. Races retention (must run well within
    # RETENTION_HOURS minus EXPORT_CORPUS_MIN_AGE_HOURS), so it's throttled
    # in minutes, not the 10s the moderation backstop uses. Only wired in
    # when CORPUS_EXPORT_ENABLED and the R2_CORPUS_* set are both present.
    # See the wiki's Configuration page.
    parser.add_argument(
        "--export-corpus-interval",
        type=int,
        default=int(os.environ.get("EXPORT_CORPUS_INTERVAL_SECONDS", 300)),
    )
    # Exact-text dedup of the accumulated corpus into per-month shards.
    # Checked once per UTC day, at or after this hour: an elapsed-seconds
    # timer would reset on every processing restart and never reach a
    # month-scale interval. compact_corpus() only touches months that
    # don't already have a shard, so the daily check is a couple of list
    # calls in the common case.
    parser.add_argument(
        "--compact-corpus-hour-utc",
        type=int,
        default=int(os.environ.get("COMPACT_CORPUS_DAILY_HOUR_UTC", 4)),
    )
    args = parser.parse_args()

    config.validate()
    signal.signal(signal.SIGTERM, _handle_sigterm)

    # The corpus export/compaction sweeps run only when explicitly switched
    # on for this environment (production) and the corpus R2 credentials
    # are present -- otherwise they are never wired into the loop at all.
    corpus_enabled = config.CORPUS_EXPORT_ENABLED and config.corpus_r2_configured()
    if config.CORPUS_EXPORT_ENABLED and not config.corpus_r2_configured():
        logger.warning("CORPUS_EXPORT_ENABLED is set but R2_CORPUS_* is incomplete -- corpus export idle")

    logger.info("starting")

    if args.once:
        pipeline.enforce_redis_capacity()
        pipeline.run_cycle(args.batch_size)
        pipeline.recheck_moderation()
        pipeline.refresh_rankings()
        pipeline.resolve_authors()
        pipeline.cleanup_old_data()
        pipeline.purge_blocked_authors()
        if corpus_enabled:
            pipeline.export_corpus()
            pipeline.compact_corpus()
        network_detector.record_clusters(
            network_detector.detect_clusters() + network_detector.detect_bluesky_funnel_cluster()
        )
        db.close()
        return

    # Public, safe-to-expose config only -- see infra/status_server.py and
    # CLAUDE.md's Service resilience section for what's deliberately
    # excluded (credentials, the heartbeat URL itself).
    status_server.start(
        port=int(os.environ.get("PORT", 8080)),
        public_config={
            "redis_max_bytes": config.REDIS_MAX_BYTES,
            "redis_soft_limit_ratio": config.REDIS_SOFT_LIMIT_RATIO,
            "r2_configured": config.r2_configured(),
            "corpus_export_enabled": corpus_enabled,
            "batch_size": args.batch_size,
            "interval_seconds": args.interval,
            "backlog_buffer_seconds": args.backlog_buffer,
            "refresh_interval_seconds": args.refresh_interval,
            "moderation_recheck_interval_seconds": args.moderation_recheck_interval,
            "purge_blocked_authors_interval_seconds": args.purge_blocked_authors_interval,
            "author_resolve_interval_seconds": args.author_resolve_interval,
            "network_detection_interval_seconds": args.network_detection_interval,
            "export_corpus_interval_seconds": args.export_corpus_interval,
            "compact_corpus_hour_utc": args.compact_corpus_hour_utc,
        },
    )

    last_refresh_time = 0.0
    last_network_detection_time = 0.0
    last_redis_guard_time = 0.0
    last_moderation_recheck_time = 0.0
    last_author_resolve_time = 0.0
    last_purge_blocked_authors_time = 0.0
    last_export_corpus_time = 0.0
    last_compact_check_date = None
    while not _shutdown:
        now = time.monotonic()
        if now - last_redis_guard_time >= args.redis_guard_interval:
            pipeline.enforce_redis_capacity()
            last_redis_guard_time = now

        processed_count = pipeline.run_cycle(args.batch_size)

        now = time.monotonic()
        if now - last_moderation_recheck_time >= args.moderation_recheck_interval:
            pipeline.recheck_moderation()
            last_moderation_recheck_time = now

        if now - last_refresh_time >= args.refresh_interval:
            pipeline.refresh_rankings()
            last_refresh_time = now

        now = time.monotonic()
        if now - last_author_resolve_time >= args.author_resolve_interval:
            pipeline.resolve_authors()
            last_author_resolve_time = now

        if now - last_network_detection_time >= args.network_detection_interval:
            network_detector.record_clusters(
                network_detector.detect_clusters() + network_detector.detect_bluesky_funnel_cluster()
            )
            last_network_detection_time = now

        pipeline.cleanup_old_data()
        if now - last_purge_blocked_authors_time >= args.purge_blocked_authors_interval:
            pipeline.purge_blocked_authors()
            last_purge_blocked_authors_time = now

        # After purge_blocked_authors so a same-cycle block has already
        # removed its rows before the export reads candidates.
        if corpus_enabled:
            if now - last_export_corpus_time >= args.export_corpus_interval:
                pipeline.export_corpus()
                last_export_corpus_time = now
            # Once per UTC day, at or after the configured hour -- and on
            # the first loop after a restart. compact_corpus() no-ops any
            # month that already has a shard.
            today_utc = datetime.now(timezone.utc)
            if _daily_task_due(today_utc, args.compact_corpus_hour_utc, last_compact_check_date):
                pipeline.compact_corpus()
                last_compact_check_date = today_utc.date()
        # Only reached if the whole cycle completed without raising - an
        # unhandled exception anywhere above crashes the process before
        # this line, which is exactly the "missed ping" a dead-man's-switch
        # monitor needs to see. No try/except here on purpose. Recording
        # cycle success here too (not just pinging) is what lets the status
        # endpoint's "degraded" field mean "not degraded since this cycle",
        # not just "never degraded since process start".
        degradation.record_cycle_success()
        heartbeat.ping(config.HEARTBEAT_URL_PROCESSING)
        if _shutdown:
            break
        time.sleep(args.interval if processed_count == 0 else args.backlog_buffer)

    db.close()


if __name__ == "__main__":
    main()
