import os
import sys

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

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
