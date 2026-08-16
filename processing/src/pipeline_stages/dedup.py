import base64
import hashlib
import os
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

import numpy as np
from datasketch import MinHash

from infra import redis_client
from text_normalize import normalize_text

# MinHash + LSH near-duplicate detection -- see the wiki's Deduplication
# page for how this works and what each of these controls. Defaults are
# an empirically-validated configuration (they catch a real near-duplicate
# pair a coarser ROWS_PER_BAND misses); treat any change as unvalidated
# until re-checked against real near-duplicate pairs.
DEDUP_NUM_PERM = int(os.environ.get("DEDUP_NUM_PERM", "128"))
DEDUP_NUM_BANDS = int(os.environ.get("DEDUP_NUM_BANDS", "16"))
if DEDUP_NUM_PERM % DEDUP_NUM_BANDS != 0:
    raise ValueError(
        f"DEDUP_NUM_PERM ({DEDUP_NUM_PERM}) must be evenly divisible by "
        f"DEDUP_NUM_BANDS ({DEDUP_NUM_BANDS})"
    )
ROWS_PER_BAND = DEDUP_NUM_PERM // DEDUP_NUM_BANDS  # derived, not independently configurable
DEDUP_SHINGLE_SIZE = int(os.environ.get("DEDUP_SHINGLE_SIZE", "4"))
DEDUP_JACCARD_THRESHOLD = float(os.environ.get("DEDUP_JACCARD_THRESHOLD", "0.7"))
# Matches processing/'s data-retention window by convention, not a shared
# constant -- keep in sync if you change either. See the wiki's
# Deduplication page for why a mismatch (this shorter than retention) is a
# real correctness risk, not just a tidiness one.
DEDUP_BAND_TTL_SECONDS = int(os.environ.get("DEDUP_BAND_TTL_SECONDS", str(24 * 60 * 60)))


def shingles(text: str, k: int = DEDUP_SHINGLE_SIZE) -> set[str]:
    words = text.split()
    if len(words) == 0:
        return set()
    if len(words) < k:
        return {" ".join(words)}
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def compute_minhash(text: str) -> MinHash:
    mh = MinHash(num_perm=DEDUP_NUM_PERM)
    for shingle in shingles(normalize_text(text)):
        mh.update(shingle.encode("utf8"))
    return mh


def band_hashes(mh: MinHash) -> list[str]:
    hv = mh.hashvalues
    hashes = []
    for band in range(DEDUP_NUM_BANDS):
        start = band * ROWS_PER_BAND
        chunk = hv[start : start + ROWS_PER_BAND]
        digest = hashlib.sha1(chunk.tobytes()).hexdigest()
        hashes.append(f"{band}:{digest}")
    return hashes


def serialize_minhash(mh: MinHash) -> str:
    # Base64 of the raw uint32 bytes, not a comma-separated decimal string --
    # roughly half the size, and this is the largest per-key Redis payload
    # in the pipeline, written on every processed post. Native byte order
    # is fine since the same container image both writes and reads it.
    return base64.b64encode(mh.hashvalues.astype(np.uint32).tobytes()).decode("ascii")


def deserialize_minhash(data: str) -> MinHash | None:
    """Returns None (treated by callers the same as no signature at all) for
    a signature that isn't decodable as a current-format MinHash -- e.g.
    still-live Redis data written under a since-changed DEDUP_NUM_PERM, or
    an older serialization format, both of which naturally age out within
    DEDUP_BAND_TTL_SECONDS of the format changing. Without this check,
    comparing it against a freshly computed MinHash raises inside
    datasketch's jaccard(), crashing the whole cycle rather than just
    skipping one stale candidate. See the wiki's Deduplication page."""
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, TypeError):
        return None
    if len(raw) != DEDUP_NUM_PERM * 4:
        return None
    mh = MinHash(num_perm=DEDUP_NUM_PERM)
    mh.hashvalues = np.frombuffer(raw, dtype=np.uint32).copy()
    return mh


class DedupIndex(Protocol):
    def find_candidates(self, hashes: list[str]) -> set[str]: ...
    def get_signatures(self, post_ids: set[str]) -> dict[str, MinHash | None]: ...
    def get_clusters(self, post_ids: list[str]) -> dict[str, str | None]: ...
    def record(self, post_id: str, mh: MinHash, hashes: list[str], cluster_id: str) -> None: ...


class RedisDedupIndex:
    """LSH band membership + MinHash signatures + cluster lookups, stored in
    Upstash Redis. All ephemeral (TTL'd) — Postgres holds the durable result.
    See the wiki's Deduplication page."""

    def __init__(self) -> None:
        self.client = redis_client.get_client()

    def find_candidates(self, hashes: list[str]) -> set[str]:
        pipe = self.client.pipeline()
        for h in hashes:
            pipe.smembers(f"lsh:band:{h}")
        results = pipe.exec()
        candidates: set[str] = set()
        for members in results:
            candidates.update(members or [])
        return candidates

    def get_signatures(self, post_ids: set[str]) -> dict[str, MinHash | None]:
        if not post_ids:
            return {}
        ids = list(post_ids)
        pipe = self.client.pipeline()
        for post_id in ids:
            pipe.get(f"mh:{post_id}")
        results = pipe.exec()
        return {
            post_id: (deserialize_minhash(data) if data else None)
            for post_id, data in zip(ids, results)
        }

    def get_clusters(self, post_ids: list[str]) -> dict[str, str | None]:
        if not post_ids:
            return {}
        pipe = self.client.pipeline()
        for post_id in post_ids:
            pipe.get(f"dedup:cluster:{post_id}")
        results = pipe.exec()
        return dict(zip(post_ids, results))

    def record(self, post_id: str, mh: MinHash, hashes: list[str], cluster_id: str) -> None:
        pipe = self.client.pipeline()
        for h in hashes:
            key = f"lsh:band:{h}"
            pipe.sadd(key, post_id)
            # nx=True: only the band's first member sets the TTL -- see the
            # wiki's Deduplication page for why a rolling TTL here is unsafe.
            pipe.expire(key, DEDUP_BAND_TTL_SECONDS, nx=True)
        pipe.set(f"mh:{post_id}", serialize_minhash(mh), ex=DEDUP_BAND_TTL_SECONDS)
        pipe.set(f"dedup:cluster:{post_id}", cluster_id, ex=DEDUP_BAND_TTL_SECONDS)
        pipe.exec()


@dataclass
class DedupResult:
    cluster_id: UUID
    is_canonical: bool


def dedup_posts(
    posts: list, index: DedupIndex, jaccard_threshold: float = DEDUP_JACCARD_THRESHOLD
) -> dict[UUID, DedupResult]:
    """Assigns each post to a dedup cluster. The first post seen for a cluster
    is canonical; later near-duplicates (Jaccard >= threshold, confirmed via
    the full MinHash signature after an LSH band match) join that cluster as
    non-canonical. Mutates `index` as it goes, so posts within the same batch
    can match each other, not just posts from prior cycles. See the wiki's
    Deduplication page."""
    results: dict[UUID, DedupResult] = {}

    for post in posts:
        mh = compute_minhash(post.text)
        hashes = band_hashes(mh)
        candidate_ids = index.find_candidates(hashes) - {str(post.id)}
        candidate_signatures = index.get_signatures(candidate_ids)

        # Cluster lookups for every Jaccard-matching candidate are batched
        # into one round trip, not fetched one at a time as each match is
        # found -- the LSH/Jaccard steps above only narrow candidates down,
        # they don't rank them, so there's no ordering benefit to checking
        # clusters one by one.
        matching_ids = [
            candidate_id
            for candidate_id, candidate_mh in candidate_signatures.items()
            if candidate_mh is not None and mh.jaccard(candidate_mh) >= jaccard_threshold
        ]
        clusters = index.get_clusters(matching_ids)
        matched_cluster = next((clusters[cid] for cid in matching_ids if clusters.get(cid)), None)

        if matched_cluster:
            cluster_id = UUID(matched_cluster)
            is_canonical = False
        else:
            cluster_id = uuid4()
            is_canonical = True

        index.record(str(post.id), mh, hashes, str(cluster_id))
        results[post.id] = DedupResult(cluster_id=cluster_id, is_canonical=is_canonical)

    return results
