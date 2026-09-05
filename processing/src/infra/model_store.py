import json
from typing import Protocol

import config
from infra import r2


class ModelStore(Protocol):
    def resolve_version(self) -> str: ...
    def fetch(self, version: str) -> tuple[bytes, dict, dict]: ...  # (onnx_bytes, vocab, config)


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
            config.R2_ACCOUNT_ID,
            config.R2_ACCESS_KEY_ID,
            config.R2_SECRET_ACCESS_KEY,
        )
        self.bucket = config.R2_BUCKET_NAME

    def get_json(self, key: str) -> dict:
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return json.loads(body)

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def resolve_version(self) -> str:
        latest = self.get_json(f"{self.prefix}/latest.json")
        return latest["version"]

    def fetch(self, version: str) -> tuple[bytes, dict, dict]:
        """model.onnx + vocab.json + config.json — the sentiment CNN's
        artifact shape. The category classifier has no vocab file (its
        TF-IDF vocabulary is baked into the exported ONNX graph), so it
        calls get_bytes/get_json directly instead of this method — see
        category_model.py."""
        key_prefix = f"{self.prefix}/{version}"
        model_bytes = self.get_bytes(f"{key_prefix}/model.onnx")
        vocab = self.get_json(f"{key_prefix}/vocab.json")
        model_config = self.get_json(f"{key_prefix}/config.json")
        return model_bytes, vocab, model_config
