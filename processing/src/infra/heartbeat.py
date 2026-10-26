import logging
import os

import requests

logger = logging.getLogger("processing")

HEARTBEAT_PING_TIMEOUT_SECONDS = int(os.environ.get("HEARTBEAT_PING_TIMEOUT_SECONDS", "5"))


def ping(url: str | None, failed: bool = False) -> None:
    """Fire-and-forget ping for a dead-man's-switch monitor (e.g.
    Healthchecks.io) - a *missed* ping is the actual alert signal, so a
    failed ping here is logged and swallowed, never raised. A monitoring
    call must never be able to take down the pipeline it's monitoring.

    failed=True hits Healthchecks.io's `<url>/fail` instead, which alerts
    immediately; the next plain ping resolves it. This is how an
    alive-but-degraded process pages, since processing/ has no public
    endpoint for an external monitor to poll."""
    if not url:
        return
    if failed:
        url = url.rstrip("/") + "/fail"
    try:
        requests.get(url, timeout=HEARTBEAT_PING_TIMEOUT_SECONDS)
    except requests.RequestException as err:
        logger.warning("heartbeat ping failed: %s", err)
