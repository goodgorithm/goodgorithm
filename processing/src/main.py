import argparse
import logging
import os
import signal
import time

import config
import pipeline
from infra import db, heartbeat, network_detector

logging.basicConfig(level=logging.INFO, format="[processing] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("processing")

_shutdown = False


def _handle_sigterm(signum, frame) -> None:
    global _shutdown
    logger.info("shutting down")
    _shutdown = True


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
    # Unlike purge_blocked_authors (an unthrottled, cheap indexed DB join),
    # this calls an external API in batches -- deliberately throttled so a
    # large backlog can't turn it into a burst of external calls. Still
    # comfortably beats --refresh-interval's 30s floor, which is what
    # actually gates a post becoming feed-visible. See the wiki's
    # Configuration page.
    parser.add_argument(
        "--moderation-recheck-interval",
        type=int,
        default=int(os.environ.get("MODERATION_RECHECK_INTERVAL_SECONDS", 10)),
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
    args = parser.parse_args()

    config.validate()
    signal.signal(signal.SIGTERM, _handle_sigterm)

    logger.info("starting")

    if args.once:
        pipeline.enforce_redis_capacity()
        pipeline.run_cycle(args.batch_size)
        pipeline.recheck_moderation()
        pipeline.refresh_rankings()
        pipeline.resolve_authors()
        pipeline.cleanup_old_data()
        pipeline.purge_blocked_authors()
        network_detector.record_clusters(network_detector.detect_clusters())
        db.close()
        return

    last_refresh_time = 0.0
    last_network_detection_time = 0.0
    last_redis_guard_time = 0.0
    last_moderation_recheck_time = 0.0
    last_author_resolve_time = 0.0
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
            network_detector.record_clusters(network_detector.detect_clusters())
            last_network_detection_time = now

        pipeline.cleanup_old_data()
        pipeline.purge_blocked_authors()
        # Only reached if the whole cycle completed without raising - an
        # unhandled exception anywhere above crashes the process before
        # this line, which is exactly the "missed ping" a dead-man's-switch
        # monitor needs to see. No try/except here on purpose.
        heartbeat.ping(config.HEARTBEAT_URL_PROCESSING)
        if _shutdown:
            break
        time.sleep(args.interval if processed_count == 0 else args.backlog_buffer)

    db.close()


if __name__ == "__main__":
    main()
