import logging
import os

import requests

logger = logging.getLogger("processing")

HEARTBEAT_PING_TIMEOUT_SECONDS = int(os.environ.get("HEARTBEAT_PING_TIMEOUT_SECONDS", "5"))


def ping(url: str | None) -> None:
    """Fire-and-forget ping for a dead-man's-switch monitor (e.g.
    Healthchecks.io) - a *missed* ping is the actual alert signal, so a
    failed ping here is logged and swallowed, never raised. A monitoring
    call must never be able to take down the pipeline it's monitoring."""
    if not url:
        return
    try:
        requests.get(url, timeout=HEARTBEAT_PING_TIMEOUT_SECONDS)
    except requests.RequestException as err:
        logger.warning("heartbeat ping failed: %s", err)
