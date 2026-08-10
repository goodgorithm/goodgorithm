import argparse
import logging
import os
import signal
import time

import config
import db
import heartbeat
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
    args = parser.parse_args()

    config.validate()
    signal.signal(signal.SIGTERM, _handle_sigterm)

    logger.info("starting")

    if args.once:
        pipeline.run_cycle(args.batch_size)
        pipeline.refresh_rankings()
        pipeline.cleanup_old_data()
        db.close()
        return

    while not _shutdown:
        pipeline.run_cycle(args.batch_size)
        pipeline.refresh_rankings()
        pipeline.cleanup_old_data()
        # Only reached if the whole cycle completed without raising - an
        # unhandled exception anywhere above crashes the process before
        # this line, which is exactly the "missed ping" a dead-man's-switch
        # monitor needs to see. No try/except here on purpose.
        heartbeat.ping(config.HEARTBEAT_URL_PROCESSING)
        if _shutdown:
            break
        time.sleep(args.interval)

    db.close()


if __name__ == "__main__":
    main()
