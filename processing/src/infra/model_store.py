import json
from pathlib import Path
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


class LocalDirModelStore:
    """Reads model artifacts from a local directory laid out exactly like
    the goodgorithm-models bucket (<root>/<prefix>/<version>/<artifact>
    plus <root>/<prefix>/latest.json), for local dev without R2
    credentials -- populated from the public GitHub Releases by
    scripts/fetch_local_models.py."""

    def __init__(self, root: str, prefix: str) -> None:
        self.prefix = prefix
        self.root = Path(root)

    def get_bytes(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def get_json(self, key: str) -> dict:
        return json.loads(self.get_bytes(key))

    def resolve_version(self) -> str:
        latest = self.get_json(f"{self.prefix}/latest.json")
        return latest["version"]


def default_store(prefix: str) -> ModelStore | None:
    """The configured model source for `prefix`, or None when there isn't
    one (every model-backed stage then fails open). Raises rather than
    choosing when both sources are set -- config.validate() stops a real
    service from starting that way, so this only guards direct callers."""
    if config.models_sources_conflict():
        raise ValueError("LOCAL_MODELS_DIR and R2_MODELS_* are both set -- use one model source")
    source = config.models_source()
    if source == "local":
        return LocalDirModelStore(config.LOCAL_MODELS_DIR, prefix)
    if source == "r2":
        return R2ModelStore(prefix)
    return None
