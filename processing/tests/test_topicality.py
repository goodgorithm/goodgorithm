from dataclasses import dataclass
from uuid import UUID, uuid4

import topicality


@dataclass
class FakePost:
    id: UUID
    text: str


class InMemoryBurstIndex:
    """Test double for topicality.BurstIndex — no network, no Redis."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def bump_entities(self, entities: list[str]) -> dict[str, int]:
        result = {}
        for entity in entities:
            self.counts[entity] = self.counts.get(entity, 0) + 1
            result[entity] = self.counts[entity]
        return result


def test_extract_entities_finds_relevant_types_only():
    entities = topicality.extract_entities(
        "NASA announced the discovery on March 3rd, with $500 million in funding."
    )
    assert entities == ["nasa"]


def test_extract_entities_empty_for_no_entities():
    assert topicality.extract_entities("Local bakery wins a small business award this year.") == []


def test_compute_tfidf_scores_ranks_distinctive_text_higher():
    texts = [
        "the the the and and and the a a a",
        "quantum entanglement breakthrough announced by researchers today",
        "the the the and and and the a a a",
    ]
    scores = topicality.compute_tfidf_scores(texts)
    assert scores[1] > scores[0]
    assert scores[1] > scores[2]


def test_compute_tfidf_scores_handles_empty_vocabulary_batch():
    # an all-stopword batch leaves TfidfVectorizer with nothing to fit —
    # should fall back to zeros, not raise.
    texts = ["the the the", "a a a", "and and and"]
    assert topicality.compute_tfidf_scores(texts) == [0.0, 0.0, 0.0]


def test_score_topicality_burst_upweights_matching_entity():
    index = InMemoryBurstIndex()
    # pre-seed the burst counter so "nasa" already looks like it's spiking
    for _ in range(topicality.BURST_THRESHOLD):
        index.bump_entities(["nasa"])

    posts = [
        FakePost(id=uuid4(), text="Scientists at NASA confirmed the new mission timeline today"),
        FakePost(id=uuid4(), text="Local bakery wins a small business award this year"),
    ]
    results = topicality.score_topicality(posts, index)

    bursting_post, quiet_post = posts
    assert results[bursting_post.id].burst_component == 1.0
    assert results[quiet_post.id].burst_component == 0.0
    # same order of magnitude of tfidf salience (both distinctive short
    # posts), but the bursting one should score higher due to the boost
    assert results[bursting_post.id].score > results[bursting_post.id].tfidf_component


def test_score_topicality_first_mention_has_minimal_burst_boost():
    # bump_entities counts the current mention too, so a first sighting
    # isn't literally zero — it's 1-of-BURST_THRESHOLD, a small nudge that
    # grows toward the full boost only as more mentions accumulate.
    index = InMemoryBurstIndex()
    posts = [
        FakePost(id=uuid4(), text="Scientists at NASA confirmed the new mission timeline"),
        FakePost(id=uuid4(), text="Local bakery wins a small business award this year"),
    ]
    results = topicality.score_topicality(posts, index)

    result = results[posts[0].id]
    assert result.burst_component == 1 / topicality.BURST_THRESHOLD
    assert result.entities == ["nasa"]
    assert result.score > result.tfidf_component
