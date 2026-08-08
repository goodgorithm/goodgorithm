from dataclasses import dataclass
from uuid import UUID, uuid4

import dedup


@dataclass
class FakePost:
    id: UUID
    text: str


class InMemoryDedupIndex:
    """Test double for dedup.DedupIndex — no network, no Redis."""

    def __init__(self) -> None:
        self.bands: dict[str, set[str]] = {}
        self.signatures: dict[str, dedup.MinHash] = {}
        self.clusters: dict[str, str] = {}

    def find_candidates(self, hashes: list[str]) -> set[str]:
        result: set[str] = set()
        for h in hashes:
            result |= self.bands.get(h, set())
        return result

    def get_signature(self, post_id: str) -> dedup.MinHash | None:
        return self.signatures.get(post_id)

    def get_cluster(self, post_id: str) -> str | None:
        return self.clusters.get(post_id)

    def record(self, post_id: str, mh: dedup.MinHash, hashes: list[str], cluster_id: str) -> None:
        for h in hashes:
            self.bands.setdefault(h, set()).add(post_id)
        self.signatures[post_id] = mh
        self.clusters[post_id] = cluster_id


def test_normalize_text_strips_urls_and_mentions():
    text = "Check this out https://example.com/x @someone great news!"
    normalized = dedup.normalize_text(text)
    assert "http" not in normalized
    assert "@someone" not in normalized
    assert "great news" in normalized


def test_shingles_handles_short_and_empty_text():
    assert dedup.shingles("") == set()
    assert dedup.shingles("hello") == {"hello"}


def test_shingles_produces_overlapping_windows():
    assert dedup.shingles("a b c d e", k=4) == {"a b c d", "b c d e"}


def test_band_hashes_deterministic():
    mh1 = dedup.compute_minhash("hello world this is a test")
    mh2 = dedup.compute_minhash("hello world this is a test")
    assert dedup.band_hashes(mh1) == dedup.band_hashes(mh2)


def test_minhash_serialize_roundtrip():
    mh = dedup.compute_minhash("hello world this is a test of serialization")
    restored = dedup.deserialize_minhash(dedup.serialize_minhash(mh))
    assert mh.jaccard(restored) == 1.0


def test_near_duplicate_posts_join_same_cluster():
    index = InMemoryDedupIndex()
    posts = [
        FakePost(
            id=uuid4(),
            text="Scientists discover a new species of frog in the Amazon rainforest, researchers say",
        ),
        FakePost(
            id=uuid4(),
            text="Scientists discover a new species of frog in the Amazon rainforest, researchers say!! 🐸",
        ),
    ]
    results = dedup.dedup_posts(posts, index)

    assert results[posts[0].id].is_canonical is True
    assert results[posts[1].id].is_canonical is False
    assert results[posts[0].id].cluster_id == results[posts[1].id].cluster_id


def test_duplicate_via_appended_link_only():
    # normalize_text strips URLs entirely, so a link-only difference should
    # be a perfect match after normalization — the common "crosspost with a
    # link" case.
    index = InMemoryDedupIndex()
    posts = [
        FakePost(id=uuid4(), text="The city council approved the new park funding today"),
        FakePost(
            id=uuid4(),
            text="The city council approved the new park funding today https://news.example.com/story",
        ),
    ]
    results = dedup.dedup_posts(posts, index)

    assert results[posts[1].id].is_canonical is False
    assert results[posts[0].id].cluster_id == results[posts[1].id].cluster_id


def test_distinct_posts_get_different_clusters():
    index = InMemoryDedupIndex()
    posts = [
        FakePost(
            id=uuid4(),
            text="Scientists discover a new species of frog in the Amazon rainforest today",
        ),
        FakePost(
            id=uuid4(),
            text="Local bakery donates a thousand loaves of bread to the food bank this weekend",
        ),
    ]
    results = dedup.dedup_posts(posts, index)

    assert results[posts[0].id].cluster_id != results[posts[1].id].cluster_id
    assert results[posts[0].id].is_canonical is True
    assert results[posts[1].id].is_canonical is True
