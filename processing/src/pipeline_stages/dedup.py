import base64
import hashlib
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import numpy as np
from datasketch import MinHash

from infra import degradation, redis_client
from util.text_normalize import normalize_text
from util.url_extract import extract_raw_url

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
# Lower bar applied only to candidates that also share a normalized source
# URL (see extract_dedup_url below) -- catches cross-"persona" syndication
# networks/campaigns reposting the same link with a different hashtag set
# or attribution tail, which fall well short of DEDUP_JACCARD_THRESHOLD on
# text alone. Independent human commentary sharing the same URL tops out
# around 0.06 Jaccard; real cross-persona duplicates start around 0.29 --
# 0.2 sits in the middle of that gap with margin on both sides. Treat any
# change as unvalidated until re-checked the same way.
DEDUP_URL_JACCARD_THRESHOLD = float(os.environ.get("DEDUP_URL_JACCARD_THRESHOLD", "0.2"))
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


def extract_dedup_url(post) -> str | None:
    """The canonical article/link URL a post is "about", for the URL-gated
    dedup tier -- a different contract from thumbnail_resolver's
    extract_link_needing_thumbnail, which only returns a URL when a
    thumbnail still needs generating. Prefers the platform's own structured
    embed (Bluesky's embed.external.uri, Mastodon's card.url) over a raw-
    text regex match, but falls back to text since Mastodon's card is
    generated asynchronously and is often still empty at ingestion time
    (same caveat extract_link_needing_thumbnail's own docstring documents).
    Strips query string/fragment before returning -- two reposts of the
    same article with different tracking params (utm_source etc.) must
    still compare equal. Bare-domain URLs (no path) are rejected -- a
    generic homepage link shared by many unrelated posts would otherwise
    become a false-positive dedup signal. See the wiki's Deduplication
    page for the empirical basis."""
    raw = extract_raw_url(post.source, post.raw_json, post.text)
    if not raw:
        return None

    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    if not parts.scheme or not parts.netloc:
        return None
    path = parts.path.rstrip("/")
    if not path:
        return None

    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


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
    def find_candidates_batch(
        self, queries: list[tuple[list[str], str | None]]
    ) -> list[tuple[set[str], set[str]]]: ...
    def get_signatures(self, post_ids: set[str]) -> dict[str, MinHash | None]: ...
    def get_clusters(self, post_ids: list[str]) -> dict[str, str | None]: ...
    def record_batch(
        self, entries: list[tuple[str, MinHash, list[str], str, str | None]]
    ) -> None: ...


class RedisDedupIndex:
    """LSH band membership + MinHash signatures + cluster lookups, stored in
    Redis. All ephemeral (TTL'd) — Postgres holds the durable result.
    See the wiki's Deduplication page."""

    def __init__(self) -> None:
        self.client = redis_client.get_client()

    def find_candidates_batch(
        self, queries: list[tuple[list[str], str | None]]
    ) -> list[tuple[set[str], set[str]]]:
        """Every post's band lookups and URL lookup for the whole batch,
        pipelined into one round trip. Result i is (lsh_candidates,
        url_candidates) for queries[i].

        Degrades to "no candidates found" for every entry -- each post then
        looks canonical/unique against prior cycles for the outage's
        duration, so real cross-cycle duplicates flood through unfiltered
        (posts can still dedup against each other within this batch, in
        memory). A real cost, not a free degrade, but the alternative is a
        total processing outage -- nothing scored at all. Self-resolving
        once Redis recovers. See the wiki's Pipeline Internals page."""
        if not queries:
            return []
        try:
            pipe = self.client.pipeline()
            for hashes, url_hash in queries:
                for h in hashes:
                    pipe.smembers(f"lsh:band:{h}")
                if url_hash is not None:
                    pipe.smembers(f"dedup:url:{url_hash}")
            results = pipe.exec()
        except Exception as exc:
            degradation.record("dedup", str(exc))
            return [(set(), set()) for _ in queries]

        degradation.clear("dedup")
        out: list[tuple[set[str], set[str]]] = []
        offset = 0
        for hashes, url_hash in queries:
            lsh_candidates: set[str] = set()
            for members in results[offset : offset + len(hashes)]:
                lsh_candidates.update(members or [])
            offset += len(hashes)

            url_candidates: set[str] = set()
            if url_hash is not None:
                url_candidates.update(results[offset] or [])
                offset += 1

            out.append((lsh_candidates, url_candidates))
        return out

    def get_signatures(self, post_ids: set[str]) -> dict[str, MinHash | None]:
        if not post_ids:
            return {}
        ids = list(post_ids)
        try:
            pipe = self.client.pipeline()
            for post_id in ids:
                pipe.get(f"mh:{post_id}")
            results = pipe.exec()
        except Exception as exc:
            # Same degrade shape as find_candidates_batch -- an empty result
            # here means no candidate is ever confirmed a match, same end
            # effect as returning None for every id.
            degradation.record("dedup", str(exc))
            return {}

        degradation.clear("dedup")
        return {
            post_id: (deserialize_minhash(data) if data else None)
            for post_id, data in zip(ids, results)
        }

    def get_clusters(self, post_ids: list[str]) -> dict[str, str | None]:
        if not post_ids:
            return {}
        try:
            pipe = self.client.pipeline()
            for post_id in post_ids:
                pipe.get(f"dedup:cluster:{post_id}")
            results = pipe.exec()
        except Exception as exc:
            degradation.record("dedup", str(exc))
            return {}

        degradation.clear("dedup")
        return dict(zip(post_ids, results))

    def record_batch(
        self, entries: list[tuple[str, MinHash, list[str], str, str | None]]
    ) -> None:
        """Writes the whole batch's LSH/URL band membership, MinHash
        signatures and cluster assignments in one round trip. Each entry is
        (post_id, mh, band_hashes, cluster_id, url_hash).

        Distinct from the read-path degrade above: a failure here leaves
        every post in the batch invisible to future dedup lookups too, not
        just unmatched against past ones -- it compounds forward for as long
        as the outage lasts."""
        if not entries:
            return
        try:
            pipe = self.client.pipeline()
            for post_id, mh, hashes, cluster_id, url_hash in entries:
                for h in hashes:
                    key = f"lsh:band:{h}"
                    pipe.sadd(key, post_id)
                    # nx=True: only the band's first member sets the TTL -- see
                    # the wiki's Deduplication page for why a rolling TTL here
                    # is unsafe.
                    pipe.expire(key, DEDUP_BAND_TTL_SECONDS, nx=True)
                if url_hash is not None:
                    url_key = f"dedup:url:{url_hash}"
                    pipe.sadd(url_key, post_id)
                    pipe.expire(url_key, DEDUP_BAND_TTL_SECONDS, nx=True)
                pipe.set(f"mh:{post_id}", serialize_minhash(mh), ex=DEDUP_BAND_TTL_SECONDS)
                pipe.set(f"dedup:cluster:{post_id}", cluster_id, ex=DEDUP_BAND_TTL_SECONDS)
            pipe.exec()
        except Exception as exc:
            degradation.record(
                "dedup", f"record_batch() failed, {len(entries)} posts now unmatchable: {exc}"
            )
            return

        degradation.clear("dedup")


@dataclass
class DedupResult:
    cluster_id: UUID
    is_canonical: bool


def dedup_posts(
    posts: list,
    index: DedupIndex,
    jaccard_threshold: float = DEDUP_JACCARD_THRESHOLD,
    url_jaccard_threshold: float = DEDUP_URL_JACCARD_THRESHOLD,
) -> dict[UUID, DedupResult]:
    """Assigns each post to a dedup cluster. The first post seen for a cluster
    is canonical; later near-duplicates join that cluster as non-canonical.
    Two ways to match an existing cluster: an LSH band match confirmed by
    the full MinHash signature at Jaccard >= jaccard_threshold (the general
    near-duplicate case), or a shared normalized source URL (see
    extract_dedup_url) confirmed at the much lower url_jaccard_threshold --
    catches cross-"persona" syndication/campaign networks reposting the
    same link with a different hashtag set or attribution tail, which fall
    well short of jaccard_threshold on text alone. A candidate
    reachable both ways gets the lower threshold, since the URL match is
    itself corroborating evidence.

    Redis is touched four times for the whole batch -- prior-cycle candidate
    lookup, signature fetch, cluster fetch, write-back -- not once per post.
    A post can still match an earlier post in the *same* batch: the two
    in-order passes below each carry an in-memory overlay (`local_*`) of what
    earlier posts in the batch contributed, checked alongside the prefetched
    prior-cycle state. See the wiki's Deduplication page."""
    results: dict[UUID, DedupResult] = {}
    if not posts:
        return results

    # Phase 1 (pure CPU): MinHash signature, LSH band hashes, source-URL hash
    # for every post.
    prepared: list[tuple] = []
    for post in posts:
        mh = compute_minhash(post.text)
        hashes = band_hashes(mh)
        url = extract_dedup_url(post)
        url_hash = hashlib.sha1(url.encode("utf8")).hexdigest() if url else None
        prepared.append((post, mh, hashes, url_hash))

    batch_ids = {str(post.id) for post, _, _, _ in prepared}

    # Phase 2 (1 round trip): every post's prior-cycle LSH/URL candidates.
    prior_candidates = index.find_candidates_batch(
        [(hashes, url_hash) for _, _, hashes, url_hash in prepared]
    )

    # Phase 3 (1 round trip): MinHash signatures for the whole prior-cycle
    # candidate union. Same-batch candidates live in `local_signatures` below.
    signature_union: set[str] = set()
    for lsh_ids, url_ids in prior_candidates:
        signature_union |= lsh_ids | url_ids
    signature_union -= batch_ids
    prior_signatures = index.get_signatures(signature_union)

    # Phase 4 (pure CPU, in post order): Jaccard-confirm each post's
    # candidates against prior-cycle signatures and earlier posts in this
    # batch; stash the confirmed matches for the cluster pass.
    local_bands: dict[str, set[str]] = {}
    local_url: dict[str, set[str]] = {}
    local_signatures: dict[str, MinHash] = {}
    per_post_matches: list[list[str]] = []

    for (post, mh, hashes, url_hash), (lsh_prior, url_prior) in zip(prepared, prior_candidates):
        pid = str(post.id)

        url_ids = set(url_prior)
        if url_hash is not None:
            url_ids |= local_url.get(url_hash, set())

        candidate_ids = set(lsh_prior) | url_ids
        for h in hashes:
            candidate_ids |= local_bands.get(h, set())
        candidate_ids.discard(pid)

        matching_ids: list[str] = []
        for cid in candidate_ids:
            cand_mh = local_signatures.get(cid)
            if cand_mh is None:
                cand_mh = prior_signatures.get(cid)
            if cand_mh is None:
                continue
            threshold = url_jaccard_threshold if cid in url_ids else jaccard_threshold
            if mh.jaccard(cand_mh) >= threshold:
                matching_ids.append(cid)
        per_post_matches.append(matching_ids)

        for h in hashes:
            local_bands.setdefault(h, set()).add(pid)
        if url_hash is not None:
            local_url.setdefault(url_hash, set()).add(pid)
        local_signatures[pid] = mh

    # Phase 5 (1 round trip): cluster ids for every prior-cycle post that
    # matched something. Same-batch matches resolve from `local_clusters`.
    cluster_union = {
        cid for matches in per_post_matches for cid in matches if cid not in batch_ids
    }
    prior_clusters = index.get_clusters(list(cluster_union))

    # Phase 6 (pure CPU, in post order): assign each post its cluster,
    # carrying this batch's own assignments forward so a later duplicate
    # joins the cluster an earlier post in the batch just created.
    local_clusters: dict[str, str] = {}
    to_record: list[tuple[str, MinHash, list[str], str, str | None]] = []

    for (post, mh, hashes, url_hash), matching_ids in zip(prepared, per_post_matches):
        pid = str(post.id)

        matched_cluster: str | None = None
        for cid in matching_ids:
            c = local_clusters.get(cid)
            if c is None:
                c = prior_clusters.get(cid)
            if c:
                matched_cluster = c
                break

        if matched_cluster:
            cluster_id = UUID(matched_cluster)
            is_canonical = False
        else:
            cluster_id = uuid4()
            is_canonical = True

        local_clusters[pid] = str(cluster_id)
        to_record.append((pid, mh, hashes, str(cluster_id), url_hash))
        results[post.id] = DedupResult(cluster_id=cluster_id, is_canonical=is_canonical)

    # Phase 7 (1 round trip): write the whole batch's band membership,
    # signatures and cluster assignments.
    index.record_batch(to_record)

    return results
