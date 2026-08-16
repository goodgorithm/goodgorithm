import os
import sys

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

# Upstash plan's byte cap for this environment, and how it's enforced --
# see redis_guard.py. Optional; defaults apply if unset. See the wiki's
# Configuration page.
REDIS_MAX_BYTES = int(os.environ.get("REDIS_MAX_BYTES", 1024 * 1024 * 1024))

# R2 / trained models — all optional, never blocks the rest of the service
# starting. See the wiki's Configuration page.
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME")
SENTIMENT_MODEL_VERSION = os.environ.get("SENTIMENT_MODEL_VERSION")
CATEGORY_MODEL_VERSION = os.environ.get("CATEGORY_MODEL_VERSION")

# Optional dead-man's-switch heartbeat. See the wiki's Configuration page.
HEARTBEAT_URL_PROCESSING = os.environ.get("HEARTBEAT_URL_PROCESSING")

# Same env var name as ingestion/'s blueskyLabels.ts -- own copy, since
# Railway doesn't share env vars across services, so both must be updated
# to stay in sync. See the wiki's Configuration page.
BLUESKY_ADULT_LABEL_VALUES = frozenset(
    v.strip()
    for v in os.environ.get("BLUESKY_ADULT_LABEL_VALUES", "porn,sexual,graphic-media,nudity").split(",")
    if v.strip()
)

_REQUIRED = {
    "DATABASE_URL": DATABASE_URL,
    "UPSTASH_REDIS_REST_URL": UPSTASH_REDIS_REST_URL,
    "UPSTASH_REDIS_REST_TOKEN": UPSTASH_REDIS_REST_TOKEN,
}


def validate() -> None:
    """Fail fast on missing required env vars. Called explicitly from
    entrypoints, not at import time — modules that only need the
    non-Redis/non-DB parts of this package (e.g. dedup.py's pure MinHash
    functions, under unit test) can import without every credential set."""
    missing = [name for name, value in _REQUIRED.items() if not value]
    if missing:
        print(f"missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def r2_configured() -> bool:
    return bool(R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME)
