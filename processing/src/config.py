import os
import sys

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

# R2 / sentiment model — all optional. Absence means the sentiment CNN
# can't load and score_sentiment() falls back to VADER; it should never
# block the rest of the service from starting.
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME")
SENTIMENT_MODEL_VERSION = os.environ.get("SENTIMENT_MODEL_VERSION")

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
