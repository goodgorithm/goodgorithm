import os
import sys

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    print("DATABASE_URL is required", file=sys.stderr)
    sys.exit(1)
