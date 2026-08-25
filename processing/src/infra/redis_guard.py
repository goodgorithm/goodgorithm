import logging
import os

from infra import redis_client

logger = logging.getLogger("processing")

# Fallback defaults for a bare enforce() call (tests, a REPL) -- the real
# production values are config.REDIS_MAX_BYTES/REDIS_SOFT_LIMIT_RATIO,
# threaded through from pipeline.py's enforce_redis_capacity(). See the
# wiki's Configuration page for why the account/plan-fact cap lives in
# config.py rather than as a local env var here.
DEFAULT_MAX_BYTES = 1024 * 1024 * 1024  # 1GB
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
# doesn't fully blind itself. A curated safety decision, not a simple
# tunable -- deliberately not an env var. See the wiki's Configuration page.
EXPENDABLE_KEY_PATTERNS = ("burst:entity:*", "cluster:*:authors")

REDIS_GUARD_SCAN_COUNT = int(os.environ.get("REDIS_GUARD_SCAN_COUNT", "500"))

# How many real keys to sample for estimate_used_memory_bytes()'s bytes-per-key
# average. Not a hardcoded bytes/key constant -- deliberately re-sampled fresh
# every check, since the key-size mix (mh:*'s ~700-byte MinHash signatures vs.
# much smaller counters like botvel:*/burst:entity:*) can drift as traffic
# composition or dedup config changes, and a stale manual constant would
# silently degrade the same way INFO memory did.
#
# The sample needs to be large: the keyspace is skewed (a numerically small
# population of large dedup keys against many small counters), so a random
# sample that's too small can easily draw few or none of the large keys and
# badly undercount the true average. Kept cheap at this size via pipelining
# (below) rather than one MEMORY USAGE round trip per sampled key.
REDIS_GUARD_MEMORY_SAMPLE_SIZE = int(os.environ.get("REDIS_GUARD_MEMORY_SAMPLE_SIZE", "2000"))


def estimate_used_memory_bytes() -> int | None:
    """Best-effort estimate of total Redis memory usage. Returns None (never
    raises) on any failure -- monitoring itself must never be able to crash
    a processing cycle, same discipline as heartbeat.ping().

    Deliberately does NOT use `INFO memory`'s `used_memory` field --
    untested against this self-hosted instance's own reporting, so trusting
    it directly is optional future work, not assumed here. `DBSIZE` and
    `MEMORY USAGE <key>` are the values this relies on instead, estimating
    total bytes as DBSIZE * (a fresh sampled average of real MEMORY USAGE reads), rather
    than trusting a single unreliable aggregate command."""
    try:
        client = redis_client.get_client()
        dbsize = client.execute(["DBSIZE"])
    except Exception:
        logger.warning("redis_guard: DBSIZE failed", exc_info=True)
        return None

    if not isinstance(dbsize, int) or dbsize < 0:
        return None
    if dbsize == 0:
        return 0

    try:
        _, sample_keys = client.scan(0, count=REDIS_GUARD_MEMORY_SAMPLE_SIZE)
        if not sample_keys:
            return None
        # One pipelined round trip for the whole sample, not one MEMORY USAGE
        # call per key -- same discipline as dedup.py/bot_filter.py/
        # topicality.py, and what makes a sample this large cheap enough to
        # run every cycle.
        pipe = client.pipeline()
        for key in sample_keys:
            pipe.execute(["MEMORY", "USAGE", key])
        sizes = pipe.exec()
        sizes = [s for s in sizes if isinstance(s, int) and s >= 0]
        if not sizes:
            return None
    except Exception:
        logger.warning("redis_guard: MEMORY USAGE sampling failed", exc_info=True)
        return None

    avg_bytes = sum(sizes) / len(sizes)
    return int(dbsize * avg_bytes)


def _scan_delete(client, pattern: str) -> int:
    deleted = 0
    cursor = 0
    while True:
        cursor, keys = client.scan(cursor, match=pattern, count=REDIS_GUARD_SCAN_COUNT)
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
    topicality writes. Logs current usage for visibility and proactively
    clears expendable data once usage nears max_bytes, rather than finding
    out via a crashed write."""
    used = estimate_used_memory_bytes()
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
