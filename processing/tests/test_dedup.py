import base64
from dataclasses import dataclass
from uuid import UUID, uuid4

import numpy as np

from pipeline_stages import dedup


@dataclass
class FakePost:
    id: UUID
    text: str
    source: str = "mastodon"
    raw_json: dict | None = None


class InMemoryDedupIndex:
    """Test double for dedup.DedupIndex — no network, no Redis."""

    def __init__(self) -> None:
        self.bands: dict[str, set[str]] = {}
        self.url_index: dict[str, set[str]] = {}
        self.signatures: dict[str, dedup.MinHash] = {}
        self.clusters: dict[str, str] = {}

    def find_candidates(self, hashes: list[str], url_hash: str | None) -> tuple[set[str], set[str]]:
        lsh_result: set[str] = set()
        for h in hashes:
            lsh_result |= self.bands.get(h, set())
        url_result = set(self.url_index.get(url_hash, set())) if url_hash else set()
        return lsh_result, url_result

    def get_signatures(self, post_ids: set[str]) -> dict[str, dedup.MinHash | None]:
        return {post_id: self.signatures.get(post_id) for post_id in post_ids}

    def get_clusters(self, post_ids: list[str]) -> dict[str, str | None]:
        return {post_id: self.clusters.get(post_id) for post_id in post_ids}

    def record(
        self,
        post_id: str,
        mh: dedup.MinHash,
        hashes: list[str],
        cluster_id: str,
        url_hash: str | None,
    ) -> None:
        for h in hashes:
            self.bands.setdefault(h, set()).add(post_id)
        if url_hash is not None:
            self.url_index.setdefault(url_hash, set()).add(post_id)
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


def test_deserialize_minhash_rejects_stale_num_perm():
    # simulates a signature written to Redis under a since-changed NUM_PERM
    # (e.g. still-live data from before a deploy) -- must be treated as no
    # usable signature, not raise, or a single stale candidate crashes the
    # whole dedup_posts cycle.
    short = np.arange(dedup.DEDUP_NUM_PERM // 2, dtype=np.uint32)
    stale_data = base64.b64encode(short.tobytes()).decode("ascii")
    assert dedup.deserialize_minhash(stale_data) is None


def test_deserialize_minhash_rejects_old_csv_format():
    # simulates a signature still live in Redis under the pre-2026-08-12
    # comma-separated-decimal encoding, during the up-to-24h window after a
    # deploy switches to base64 -- must be treated as no usable signature,
    # not raise.
    old_format_data = ",".join(str(v) for v in range(dedup.DEDUP_NUM_PERM))
    assert dedup.deserialize_minhash(old_format_data) is None


def test_dedup_posts_skips_candidate_with_unusable_signature():
    # a candidate reachable via LSH banding whose signature came back None --
    # the shape get_signatures ends up in for a stale-NUM_PERM Redis entry,
    # since RedisDedupIndex.get_signatures runs every value through
    # deserialize_minhash. Must be skipped like a genuinely missing
    # signature, not crash the cycle.
    index = InMemoryDedupIndex()
    stale_id = str(uuid4())
    real_mh = dedup.compute_minhash("Scientists discover a new species of frog")
    index.signatures[stale_id] = None
    for h in dedup.band_hashes(real_mh):
        index.bands.setdefault(h, set()).add(stale_id)

    post = FakePost(id=uuid4(), text="Scientists discover a new species of frog")
    results = dedup.dedup_posts([post], index)

    assert results[post.id].is_canonical is True


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


def test_extract_dedup_url_prefers_mastodon_card_over_text():
    post = FakePost(
        id=uuid4(),
        text="Check this out https://example.com/text-link",
        source="mastodon",
        raw_json={"card": {"url": "https://example.com/article?utm_source=flipboard"}},
    )
    assert dedup.extract_dedup_url(post) == "https://example.com/article"


def test_extract_dedup_url_prefers_bluesky_embed_over_text():
    post = FakePost(
        id=uuid4(),
        text="Check this out https://example.com/text-link",
        source="bluesky",
        raw_json={
            "commit": {
                "record": {
                    "embed": {
                        "$type": "app.bsky.embed.external",
                        "external": {"uri": "https://example.com/article?ref=app"},
                    }
                }
            }
        },
    )
    assert dedup.extract_dedup_url(post) == "https://example.com/article"


def test_extract_dedup_url_falls_back_to_text_when_no_structured_embed():
    # Mastodon's card is generated asynchronously and is often still empty
    # at ingestion time -- must still find the URL directly in the text.
    post = FakePost(
        id=uuid4(), text="Big news https://example.com/story", source="mastodon", raw_json={}
    )
    assert dedup.extract_dedup_url(post) == "https://example.com/story"


def test_extract_dedup_url_strips_query_and_fragment():
    post = FakePost(
        id=uuid4(),
        text="https://example.com/story?utm_source=flipboard&utm_medium=activitypub#section",
        raw_json={},
    )
    assert dedup.extract_dedup_url(post) == "https://example.com/story"


def test_extract_dedup_url_rejects_bare_domain():
    # A generic homepage link shared by many unrelated posts shouldn't
    # become a false-positive dedup signal.
    post = FakePost(id=uuid4(), text="Check out https://example.com", raw_json={})
    assert dedup.extract_dedup_url(post) is None


def test_extract_dedup_url_returns_none_when_no_url_present():
    post = FakePost(id=uuid4(), text="No links here, just words", raw_json={})
    assert dedup.extract_dedup_url(post) is None


def test_url_matched_posts_merge_below_main_threshold():
    # Mirrors the real cross-"persona" Flipboard syndication case behind
    # issue #53: same article URL, different attribution tail, Jaccard
    # comfortably below DEDUP_JACCARD_THRESHOLD but above
    # DEDUP_URL_JACCARD_THRESHOLD.
    index = InMemoryDedupIndex()
    url = "https://www.dutchovendaddy.com/super-nachos"
    posts = [
        FakePost(
            id=uuid4(),
            text=(
                "The BEST Super Nacho Dip https://www.dutchovendaddy.com/super-nachos/"
                "?utm_source=flipboard&utm_medium=activitypub Posted into "
                "APPETIZERS FOR PARTIES AND GAME DAYS @appetizers-for-parties-and-game-days-LisaMarcAurele"
            ),
        ),
        FakePost(
            id=uuid4(),
            text=(
                "The BEST Super Nacho Dip https://www.dutchovendaddy.com/super-nachos/"
                "?utm_source=flipboard&utm_medium=activitypub Posted into "
                "EPIC Appetizers, Snacks & Treats Recipes @epic-appetizers-snacks-treats-recipes-TropRockin"
            ),
        ),
    ]
    assert dedup.extract_dedup_url(posts[0]) == url
    assert dedup.extract_dedup_url(posts[1]) == url

    results = dedup.dedup_posts(posts, index)

    assert results[posts[0].id].cluster_id == results[posts[1].id].cluster_id
    assert results[posts[1].id].is_canonical is False


def test_url_matched_posts_with_dissimilar_commentary_stay_separate():
    # Mirrors the real independent-commentary counter-example checked
    # against issue #53: same article URL, genuinely different human
    # commentary, Jaccard near zero -- must NOT merge just because the
    # URL matches. This is the guard the two-tier threshold exists for.
    index = InMemoryDedupIndex()
    posts = [
        FakePost(
            id=uuid4(),
            text=(
                "Flock really is building the infrastructure for authoritarianism. "
                "The massive pushback they are experiencing right now is because "
                "people recognize this fact. https://www.wired.com/story/flock-safety-os-investigate/"
            ),
        ),
        FakePost(
            id=uuid4(),
            text=(
                "NEW: Flock has said for years that its cameras cannot track "
                "individuals. We found the code for its new AI tool. It's preloaded "
                "with prompts like find me witness and find relatives. "
                "https://www.wired.com/story/flock-safety-os-investigate/"
            ),
        ),
    ]
    same_url = dedup.extract_dedup_url(posts[0])
    assert same_url == dedup.extract_dedup_url(posts[1])

    results = dedup.dedup_posts(posts, index)

    assert results[posts[0].id].cluster_id != results[posts[1].id].cluster_id
    assert results[posts[0].id].is_canonical is True
    assert results[posts[1].id].is_canonical is True


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
