import logging

from infra import redis_client

logger = logging.getLogger("processing")

# Upstash's current plan cap on both staging and production (2026-08-12).
# Runtime-configurable via config.REDIS_MAX_BYTES (REDIS_MAX_BYTES env var)
# since the cap is an account/plan fact, not something derivable from code,
# and can change independently of a deploy.
DEFAULT_MAX_BYTES = 1024 * 1024 * 1024  # 1GB

# Start proactively clearing expendable data once usage crosses this
# fraction of max_bytes, instead of writing blind until Upstash starts
# rejecting commands outright and crashing the process -- exactly what
# happened 2026-08-12: production crash-looped for hours once usage reached
# the 1GB cap, with zero prior visibility into how close it was.
DEFAULT_SOFT_LIMIT_RATIO = 0.85

# Cleared, in this order, when the soft limit is hit. Deliberately excludes
# dedup's own state (lsh:band:*, mh:*, dedup:cluster:*) -- silently losing
# that would let duplicate content back into the feed without anyone
# noticing, which is a worse failure mode than the loud crash this guard
# exists to prevent. burst:entity:* is explicitly a short-lived "spiking
# right now" signal (topicality.py) with no correctness cost if cleared
# early. cluster:*:authors is bot_filter's secondary self-dup signal --
# clearing it early just resets self-dup detection for clusters currently in
# flight; botvel:* (fixed-window velocity) is untouched, so bot filtering
# doesn't fully blind itself.
EXPENDABLE_KEY_PATTERNS = ("burst:entity:*", "cluster:*:authors")

_SCAN_COUNT = 500


def parse_used_memory_bytes(info_output: str) -> int | None:
    """Parses `used_memory` out of a raw `INFO memory` response. A standalone
    function so the parsing logic is unit-testable without a live Redis
    connection."""
    for line in info_output.splitlines():
        line = line.strip()
        if line.startswith("used_memory:"):
            try:
                return int(line.split(":", 1)[1])
            except ValueError:
                return None
    return None


def get_used_memory_bytes() -> int | None:
    """Best-effort read of Redis's own memory accounting. Returns None (never
    raises) on any failure -- monitoring itself must never be able to crash
    a processing cycle, same discipline as heartbeat.ping()."""
    try:
        client = redis_client.get_client()
        raw = client.execute(["INFO", "memory"])
    except Exception:
        logger.warning("redis_guard: INFO memory failed", exc_info=True)
        return None
    return parse_used_memory_bytes(str(raw))


def _scan_delete(client, pattern: str) -> int:
    deleted = 0
    cursor = 0
    while True:
        cursor, keys = client.scan(cursor, match=pattern, count=_SCAN_COUNT)
        if keys:
            deleted += client.delete(*keys)
        if cursor == 0:
            break
    return deleted


def clear_expendable_data() -> int:
    client = redis_client.get_client()
    total = 0
    for pattern in EXPENDABLE_KEY_PATTERNS:
        total += _scan_delete(client, pattern)
    return total


def enforce(max_bytes: int = DEFAULT_MAX_BYTES, soft_limit_ratio: float = DEFAULT_SOFT_LIMIT_RATIO) -> None:
    """Called once per processing cycle, before that cycle's dedup/bot-filter/
    topicality writes. Logs current usage for visibility (there was
    previously none at all) and proactively clears expendable data once
    usage nears max_bytes, rather than finding out via a crashed write."""
    used = get_used_memory_bytes()
    if used is None:
        return

    ratio = used / max_bytes
    logger.info("redis usage: %d/%d bytes (%.1f%% of cap)", used, max_bytes, ratio * 100)

    if ratio < soft_limit_ratio:
        return

    try:
        deleted = clear_expendable_data()
    except Exception:
        # A guard failure must never crash the cycle it's protecting.
        logger.warning("redis_guard: clear_expendable_data failed", exc_info=True)
        return

    logger.warning(
        "redis usage at %.1f%% of %d-byte cap -- cleared %d expendable keys",
        ratio * 100,
        max_bytes,
        deleted,
    )
