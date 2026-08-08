import json
from typing import Protocol

import boto3

import config

SENTIMENT_PREFIX = "sentiment-cnn"


class ModelStore(Protocol):
    def resolve_version(self) -> str: ...
    def fetch(self, version: str) -> tuple[bytes, dict, dict]: ...  # (onnx_bytes, vocab, config)


class R2ModelStore:
    """Cloudflare R2 is S3-API-compatible, so boto3's S3 client works
    against it directly. Versions under sentiment-cnn/ are immutable once
    published; sentiment-cnn/latest.json is the only mutable object — a
    deliberately minimal "registry", not a full model versioning system."""

    def __init__(self) -> None:
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=config.R2_ACCESS_KEY_ID,
            aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
            region_name="auto",
        )
        self.bucket = config.R2_BUCKET_NAME

    def _get_json(self, key: str) -> dict:
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return json.loads(body)

    def _get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def resolve_version(self) -> str:
        if config.SENTIMENT_MODEL_VERSION:
            return config.SENTIMENT_MODEL_VERSION
        latest = self._get_json(f"{SENTIMENT_PREFIX}/latest.json")
        return latest["version"]

    def fetch(self, version: str) -> tuple[bytes, dict, dict]:
        prefix = f"{SENTIMENT_PREFIX}/{version}"
        model_bytes = self._get_bytes(f"{prefix}/model.onnx")
        vocab = self._get_json(f"{prefix}/vocab.json")
        model_config = self._get_json(f"{prefix}/config.json")
        return model_bytes, vocab, model_config
