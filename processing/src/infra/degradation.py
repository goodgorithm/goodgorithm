import logging
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger("processing")

# In-memory, process-local only -- same trust level as main.py's own
# loop-local throttle-timer variables, not a durable record. A restart
# clears this, which is correct: it answers "is anything degraded right
# now," not "what degraded historically" (that's what logs are for).


@dataclass
class DegradationEvent:
    message: str
    at: datetime


_last_degradation: dict[str, DegradationEvent] = {}
_last_cycle_success_at: datetime | None = None


def record(subsystem: str, message: str) -> None:
    """Called from a Redis call site's except block instead of a bare
    logger.warning -- keeps the failure visible in logs (as before) while
    also making it readable by the status endpoint without waiting for
    someone to go looking through logs first."""
    _last_degradation[subsystem] = DegradationEvent(message, datetime.now(timezone.utc))
    logger.warning("degraded: %s - %s", subsystem, message)


def clear(subsystem: str) -> None:
    """Called on a subsequent successful call to the same subsystem, so a
    resolved outage doesn't stay reported as degraded forever."""
    _last_degradation.pop(subsystem, None)


def snapshot() -> dict[str, dict]:
    return {
        name: {"last_degraded_at": event.at.isoformat(), "message": event.message}
        for name, event in _last_degradation.items()
    }


def record_cycle_success() -> None:
    global _last_cycle_success_at
    _last_cycle_success_at = datetime.now(timezone.utc)


def last_cycle_success_at() -> str | None:
    return _last_cycle_success_at.isoformat() if _last_cycle_success_at else None
