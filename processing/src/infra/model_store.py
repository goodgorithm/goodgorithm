import json
from typing import Protocol

import config
from infra import r2


class ModelStore(Protocol):
    prefix: str

    def resolve_version(self) -> str: ...
    def get_bytes(self, key: str) -> bytes: ...
    def get_json(self, key: str) -> dict: ...


class R2ModelStore:
    """Cloudflare R2 is S3-API-compatible, so boto3's S3 client works
    against it directly. Versions under <prefix>/ are immutable once
    published; <prefix>/latest.json is the only mutable object — a
    deliberately minimal "registry", not a full model versioning system.
    Generalized across model types via `prefix` rather than forked per
    model — see training/r2_release.py's MODEL_REGISTRY for the same shape
    on the publishing side."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.client = r2.client(
            config.R2_MODELS_ACCOUNT_ID,
            config.R2_MODELS_ACCESS_KEY_ID,
            config.R2_MODELS_SECRET_ACCESS_KEY,
        )
        self.bucket = config.R2_MODELS_BUCKET_NAME

    def get_json(self, key: str) -> dict:
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return json.loads(body)

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def resolve_version(self) -> str:
        latest = self.get_json(f"{self.prefix}/latest.json")
        return latest["version"]
