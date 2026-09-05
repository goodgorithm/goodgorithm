import config
from infra import r2


class CorpusStore:
    """Read/write access to the goodgorithm-corpus R2 bucket — the
    long-lived post-text archive the export sweep appends to and the
    compaction sweep rewrites into monthly shards. Separate credential set
    and bucket from R2ModelStore (which is read-only against
    goodgorithm-models).

    Objects are immutable once written under `raw/`; `shards/YYYY-MM…` is
    rebuilt idempotently by compaction. No append primitive exists in S3/R2
    — every write is a whole-object PUT."""

    def __init__(self) -> None:
        self.client = r2.client(
            config.R2_CORPUS_ACCOUNT_ID,
            config.R2_CORPUS_ACCESS_KEY_ID,
            config.R2_CORPUS_SECRET_ACCESS_KEY,
        )
        self.bucket = config.R2_CORPUS_BUCKET_NAME

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/gzip") -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def put_fileobj(self, key: str, fileobj, content_type: str = "application/gzip") -> None:
        """For compaction, which streams a month of deduped records through
        a temp file rather than holding it in memory."""
        self.client.upload_fileobj(
            fileobj, self.bucket, key, ExtraArgs={"ContentType": content_type}
        )

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys

    def delete_keys(self, keys: list[str]) -> None:
        """S3 DeleteObjects caps at 1000 keys per call."""
        for i in range(0, len(keys), 1000):
            chunk = keys[i : i + 1000]
            self.client.delete_objects(
                Bucket=self.bucket, Delete={"Objects": [{"Key": k} for k in chunk]}
            )
