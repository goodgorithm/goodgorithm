import base64
import hashlib
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

import numpy as np
from datasketch import MinHash

import redis_client
from text_normalize import normalize_text

# NUM_PERM=128/NUM_BANDS=16 (ROWS_PER_BAND=8) is the empirically verified
# config -- it catches a real near-duplicate pair (0.773 Jaccard) that a
# coarser ROWS_PER_BAND misses, since match probability depends
# exponentially on rows-per-band, not linearly on band count. This was
# temporarily halved (NUM_PERM=64/NUM_BANDS=8, same ROWS_PER_BAND=8) to cut
# Redis command volume under the old hard-capped free tier; restored now
# that Upstash is on a rate-limited (not hard-capped) plan.
NUM_PERM = 128
NUM_BANDS = 16
ROWS_PER_BAND = NUM_PERM // NUM_BANDS
SHINGLE_SIZE = 4
JACCARD_THRESHOLD = 0.7
# matches RETENTION_HOURS (pipeline.py) -- no point deduplicating against a
# post whose row will already have been deleted from Postgres.
BAND_TTL_SECONDS = 24 * 60 * 60

def shingles(text: str, k: int = SHINGLE_SIZE) -> set[str]:
    words = text.split()
    if len(words) == 0:
        return set()
    if len(words) < k:
        return {" ".join(words)}
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def compute_minhash(text: str) -> MinHash:
    mh = MinHash(num_perm=NUM_PERM)
    for shingle in shingles(normalize_text(text)):
        mh.update(shingle.encode("utf8"))
    return mh


def band_hashes(mh: MinHash) -> list[str]:
    hv = mh.hashvalues
    hashes = []
    for band in range(NUM_BANDS):
        start = band * ROWS_PER_BAND
        chunk = hv[start : start + ROWS_PER_BAND]
        digest = hashlib.sha1(chunk.tobytes()).hexdigest()
        hashes.append(f"{band}:{digest}")
    return hashes


def serialize_minhash(mh: MinHash) -> str:
    # Base64 of the raw uint32 bytes rather than a comma-separated decimal
    # string -- ~1.3KB down to ~700 bytes per signature (2026-08-12: this is
    # the single largest per-key Redis payload in the pipeline, written on
    # every processed post). Native byte order is fine since the same
    # container image both writes and reads it.
    return base64.b64encode(mh.hashvalues.astype(np.uint32).tobytes()).decode("ascii")


def deserialize_minhash(data: str) -> MinHash | None:
    """Returns None (treated by callers the same as no signature at all) for
    a signature that isn't decodable as a current-format MinHash -- e.g.
    still-live Redis data written under a since-changed NUM_PERM, or (as of
    2026-08-12) the older comma-separated-decimal encoding, both of which
    naturally age out within BAND_TTL_SECONDS of a format change deploying.
    Without this check, comparing it against a freshly computed MinHash
    raises inside datasketch's jaccard(), crashing the whole cycle rather
    than just skipping one stale candidate."""
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, TypeError):
        return None
    if len(raw) != NUM_PERM * 4:
        return None
    mh = MinHash(num_perm=NUM_PERM)
    mh.hashvalues = np.frombuffer(raw, dtype=np.uint32).copy()
    return mh


class DedupIndex(Protocol):
    def find_candidates(self, hashes: list[str]) -> set[str]: ...
    def get_signatures(self, post_ids: set[str]) -> dict[str, MinHash | None]: ...
    def get_cluster(self, post_id: str) -> str | None: ...
    def record(self, post_id: str, mh: MinHash, hashes: list[str], cluster_id: str) -> None: ...


class RedisDedupIndex:
    """LSH band membership + MinHash signatures + cluster lookups, stored in
    Upstash Redis. All ephemeral (TTL'd) — Postgres holds the durable result."""

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

    def get_cluster(self, post_id: str) -> str | None:
        return self.client.get(f"dedup:cluster:{post_id}")

    def record(self, post_id: str, mh: MinHash, hashes: list[str], cluster_id: str) -> None:
        pipe = self.client.pipeline()
        for h in hashes:
            key = f"lsh:band:{h}"
            pipe.sadd(key, post_id)
            # nx=True: only the band's first member sets the TTL. Without
            # this, a "hot" band (a widely-copied post/meme/spam wave that
            # keeps landing in the same band bucket) had its 24h TTL pushed
            # forward on every single hit, letting it live indefinitely
            # instead of on a fixed 24h window (2026-08-12 incident).
            pipe.expire(key, BAND_TTL_SECONDS, nx=True)
        pipe.set(f"mh:{post_id}", serialize_minhash(mh), ex=BAND_TTL_SECONDS)
        pipe.set(f"dedup:cluster:{post_id}", cluster_id, ex=BAND_TTL_SECONDS)
        pipe.exec()


@dataclass
class DedupResult:
    cluster_id: UUID
    is_canonical: bool


def dedup_posts(
    posts: list, index: DedupIndex, jaccard_threshold: float = JACCARD_THRESHOLD
) -> dict[UUID, DedupResult]:
    """Assigns each post to a dedup cluster. The first post seen for a cluster
    is canonical; later near-duplicates (Jaccard >= threshold, confirmed via
    the full MinHash signature after an LSH band match) join that cluster as
    non-canonical. Mutates `index` as it goes, so posts within the same batch
    can match each other, not just posts from prior cycles."""
    results: dict[UUID, DedupResult] = {}

    for post in posts:
        mh = compute_minhash(post.text)
        hashes = band_hashes(mh)
        candidate_ids = index.find_candidates(hashes) - {str(post.id)}
        candidate_signatures = index.get_signatures(candidate_ids)

        matched_cluster: str | None = None
        for candidate_id, candidate_mh in candidate_signatures.items():
            if candidate_mh is None:
                continue
            if mh.jaccard(candidate_mh) >= jaccard_threshold:
                matched_cluster = index.get_cluster(candidate_id)
                if matched_cluster:
                    break

        if matched_cluster:
            cluster_id = UUID(matched_cluster)
            is_canonical = False
        else:
            cluster_id = uuid4()
            is_canonical = True

        index.record(str(post.id), mh, hashes, str(cluster_id))
        results[post.id] = DedupResult(cluster_id=cluster_id, is_canonical=is_canonical)

    return results
