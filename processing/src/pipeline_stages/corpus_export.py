import gzip
import json
import uuid
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from infra.db import ExportablePost

# Raw text plus the minimum metadata to filter the corpus later without
# re-deriving it. Deliberately no sentiment_score (circular for training a
# sentiment model), no author id, no engagement counts.
RECORD_FIELDS = (
    "text",
    "source",
    "created_at",
    "category",
    "category_method",
    "pipeline_version",
    "dedup_cluster_id",
)


@dataclass
class CorpusObject:
    key: str
    data: bytes
    raw_post_ids: list


def _record(post: ExportablePost) -> dict:
    return {
        "text": post.text,
        "source": post.source,
        "created_at": post.created_at.isoformat(),
        "category": post.category,
        "category_method": post.category_method,
        "pipeline_version": post.pipeline_version,
        "dedup_cluster_id": str(post.dedup_cluster_id),
    }


def _serialize(records: list[dict]) -> bytes:
    body = "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records)
    return gzip.compress(body.encode("utf-8"))


def object_key(prefix: str, source: str, day: datetime, first_epoch: int) -> str:
    """`<prefix>/raw/YYYY/MM/DD/<source>-<epoch>-<uuid>.ndjson.gz`. The
    epoch (earliest processed_at in the batch) keeps names roughly ordered;
    the uuid makes every write a distinct immutable object with no
    collision even for two batches of the same source on the same day."""
    return (
        f"{prefix}/raw/{day:%Y/%m/%d}/{source}-{first_epoch}-{uuid.uuid4().hex}.ndjson.gz"
    )


def build_objects(prefix: str, posts: list[ExportablePost]) -> list[CorpusObject]:
    """Groups a sweep batch by (source, processed_at date) and returns one
    gzipped NDJSON object per group, each carrying the raw_post_ids it
    covers so the caller can mark exactly those exported once the PUT
    succeeds."""
    groups: dict[tuple[str, str], list[ExportablePost]] = defaultdict(list)
    for post in posts:
        groups[(post.source, post.processed_at.strftime("%Y-%m-%d"))].append(post)

    objects: list[CorpusObject] = []
    for (source, _day), group in groups.items():
        group.sort(key=lambda p: p.processed_at)
        first_epoch = int(group[0].processed_at.timestamp())
        objects.append(
            CorpusObject(
                key=object_key(prefix, source, group[0].processed_at, first_epoch),
                data=_serialize([_record(p) for p in group]),
                raw_post_ids=[p.raw_post_id for p in group],
            )
        )
    return objects


def iter_records(data: bytes) -> Iterator[dict]:
    for line in gzip.decompress(data).decode("utf-8").splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)


def dedup_key(record: dict) -> str:
    """Exact-match key for the monthly compaction pass -- the same post
    text syndicated across sources, or re-exported inside the retry window,
    collapses to one record. `.strip()` only, so genuinely different
    whitespace stays distinct."""
    return record.get("text", "").strip()
