import argparse
import logging
import os
import signal
import time

import config
import db
import heartbeat
import network_detector
import pipeline

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
    # Backlog-aware sleep: only take the full --interval as idle time when a
    # cycle genuinely had nothing to process. A full unconditional sleep after
    # every cycle regardless of backlog depth was measured 2026-08-10 costing
    # ~300s of pure idle time on top of every ~200-230s cycle (real
    # cycle-to-cycle gaps were ~510s against a 300s configured interval) -
    # fine for an occasional idle moment, not for the sustained deep backlog
    # confirmed the same day (ingestion outpacing processing ~39x). A short
    # fixed buffer instead of looping with zero delay avoids hammering
    # Postgres/Redis in a tight loop while there's real backlog. Configurable
    # (2026-08-11) so a low-traffic environment can use a larger buffer
    # without hardcoding a second code path.
    parser.add_argument(
        "--backlog-buffer",
        type=int,
        default=int(os.environ.get("PROCESSING_BACKLOG_BUFFER_SECONDS", 3)),
    )
    # refresh_rankings() rebuilds the full MMR similarity matrices from
    # scratch (ranking.py's _similarity_matrix) over the whole candidate
    # pool - real O(n^2) compute, ~96MB of dense arrays at the current
    # MMR_CANDIDATE_POOL_SIZE cap. Running it on literally every loop
    # iteration (as often as every --backlog-buffer seconds under any
    # backlog) redoes that work almost entirely from scratch for a pool
    # that's barely changed since the last run. rank_score being up to
    # this many seconds stale is imperceptible - feed freshness is
    # dominated by run_cycle inserting new posts continuously, not by how
    # fast the diversity re-ranking catches up.
    parser.add_argument(
        "--refresh-interval",
        type=int,
        default=int(os.environ.get("REFRESH_RANKINGS_INTERVAL_SECONDS", 30)),
    )
    # network_detector.detect_clusters() is a full-table aggregate over
    # raw_posts (issue #44), structurally heavier than a normal cycle and
    # looking for a slow-forming pattern (a coordinated bot network), not
    # something needing near-real-time freshness -- throttled far less
    # frequently than refresh_rankings above.
    parser.add_argument(
        "--network-detection-interval",
        type=int,
        default=int(os.environ.get("NETWORK_DETECTION_INTERVAL_SECONDS", 3600)),
    )
    args = parser.parse_args()

    config.validate()
    signal.signal(signal.SIGTERM, _handle_sigterm)

    logger.info("starting")

    if args.once:
        pipeline.enforce_redis_capacity()
        pipeline.run_cycle(args.batch_size)
        pipeline.refresh_rankings()
        pipeline.cleanup_old_data()
        pipeline.purge_blocked_authors()
        network_detector.record_clusters(network_detector.detect_clusters())
        db.close()
        return

    last_refresh_time = 0.0
    last_network_detection_time = 0.0
    while not _shutdown:
        pipeline.enforce_redis_capacity()
        processed_count = pipeline.run_cycle(args.batch_size)

        now = time.monotonic()
        if now - last_refresh_time >= args.refresh_interval:
            pipeline.refresh_rankings()
            last_refresh_time = now

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
