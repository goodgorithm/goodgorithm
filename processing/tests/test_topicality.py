from dataclasses import dataclass
from uuid import UUID, uuid4

import numpy as np
import spacy

from pipeline_stages import topicality


@dataclass
class FakePost:
    id: UUID
    text: str


class InMemoryBurstIndex:
    """Test double for topicality.BurstIndex — no network, no Redis."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def bump_entities(self, entities_by_post: list[list[str]]) -> list[dict[str, int]]:
        results = []
        for entities in entities_by_post:
            result = {}
            for entity in entities:
                self.counts[entity] = self.counts.get(entity, 0) + 1
                result[entity] = self.counts[entity]
            results.append(result)
        return results


def test_extract_entities_finds_relevant_types_only():
    entities = topicality.extract_entities(
        "NASA announced the discovery on March 3rd, with $500 million in funding."
    )
    assert entities == ["nasa"]


def test_extract_entities_empty_for_no_entities():
    assert topicality.extract_entities("Local bakery wins a small business award this year.") == []


def test_extract_entities_typed_includes_the_label():
    typed = topicality.extract_entities_typed(
        "NASA announced the discovery on March 3rd, with $500 million in funding."
    )
    assert typed == [("nasa", "ORG")]


def test_extract_entities_typed_dedupes_by_text_keeping_first_label():
    typed = topicality.extract_entities_typed("NASA and NASA again announced the mission.")
    assert typed == [("nasa", "ORG")]


def test_entities_from_doc_rejects_url_shaped_entities():
    # issue #55: spaCy's NER occasionally mis-tags a URL span with a
    # relevant label (ORG/GPE seen in real production data) -- forces a
    # URL entity via doc.set_ents so this is deterministic regardless of
    # what the real model actually predicts for this input.
    nlp = topicality._get_nlp()
    doc = nlp("Check out https://example.com/story for more")
    url_token_idx = next(i for i, t in enumerate(doc) if t.text.startswith("https"))
    span = spacy.tokens.Span(doc, url_token_idx, url_token_idx + 1, label="ORG")
    doc.set_ents([span])

    assert topicality._entities_from_doc(doc) == []


def test_extract_entities_is_consistent_with_extract_entities_typed():
    text = "Scientists at NASA confirmed the new mission timeline today"
    assert topicality.extract_entities(text) == [e for e, _label in topicality.extract_entities_typed(text)]


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


def test_compute_tfidf_top_terms_are_real_terms_from_the_batch():
    # taxonomy.categorize() matches against these -- they must be actual
    # vocabulary strings, not indices or weights.
    texts = [
        "quantum entanglement breakthrough announced by researchers today",
        "solar power panels installed on the community center roof",
    ]
    _, top_terms = topicality._compute_tfidf(texts)
    assert len(top_terms) == 2
    assert all(isinstance(term, str) for term in top_terms[0])
    assert set(top_terms[0]).issubset(set(texts[0].split()))
    assert set(top_terms[1]).issubset(set(texts[1].split()))


def test_compute_tfidf_top_terms_empty_for_empty_vocabulary_batch():
    texts = ["the the the", "a a a"]
    _, top_terms = topicality._compute_tfidf(texts)
    assert top_terms == [[], []]


def test_score_topicality_result_includes_top_terms():
    index = InMemoryBurstIndex()
    posts = [FakePost(id=uuid4(), text="quantum entanglement breakthrough announced by researchers today")]
    results = topicality.score_topicality(posts, index)
    assert results[posts[0].id].top_terms
    assert all(isinstance(term, str) for term in results[posts[0].id].top_terms)


def test_score_topicality_burst_upweights_matching_entity():
    index = InMemoryBurstIndex()
    # pre-seed the burst counter so "nasa" already looks like it's spiking
    for _ in range(topicality.TOPICALITY_BURST_THRESHOLD):
        index.bump_entities([["nasa"]])

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


def test_top_k_mean_single_token_is_undiscounted():
    # A genuine single-term post must not be discounted -- 1 ** ALPHA == 1
    # for any ALPHA, so its score still depends entirely on that term's own
    # weight. This is what keeps the discount from reopening the
    # L2-normalization regression (56ee036) that inflated single-word/emoji
    # posts to a flat ceiling.
    assert topicality._top_k_mean(np.array([1.0]), 3, token_count=1) == 1.0


def test_top_k_mean_discount_grows_with_token_count():
    # Fixed top-3 values in both cases; only token_count differs, isolating
    # the discount's dependence on actual text length rather than on how
    # many distinct terms survived stopword filtering.
    values = np.array([5.0, 4.0, 3.0])
    score_short = topicality._top_k_mean(values, 3, token_count=3)
    score_long = topicality._top_k_mean(values, 3, token_count=20)
    assert score_short < 4.0  # discount already engages once token_count > 1
    assert score_long < score_short  # more tokens -> larger discount


def test_top_k_mean_diversity_discount_is_a_noop_when_every_token_is_distinct():
    # token_count == nnz (every token that survived stopword filtering is
    # its own distinct term) means the diversity ratio is 1, so the
    # diversity discount contributes nothing beyond the length discount --
    # varied vocabulary shouldn't be penalized just for being long.
    values = np.array([5.0, 4.0, 3.0])
    with_diversity = topicality._top_k_mean(values, 3, token_count=3)
    length_only = float(np.mean(values)) / (3**topicality.TOPICALITY_LENGTH_NORM_ALPHA)
    assert with_diversity == length_only


def test_top_k_mean_discounts_repetition_even_when_only_one_term_survives():
    # A repeated non-stopword term collapses to a single surviving TF-IDF
    # entry (e.g. "the best" x10 -> only "best" has a nonzero weight, so
    # nnz==1 same as a genuinely short post would have). The length discount
    # alone (keyed on token_count) still applies here, but it's the
    # diversity discount -- token_count/nnz, large when one term dominates a
    # long post -- that does most of the work distinguishing this case from
    # a genuine single-term post.
    weight = np.array([5.0])
    undiscounted = topicality._top_k_mean(weight, 3, token_count=1)
    discounted = topicality._top_k_mean(weight, 3, token_count=20)
    assert discounted < undiscounted
    nnz = weight.size
    length_discount = 20**topicality.TOPICALITY_LENGTH_NORM_ALPHA
    diversity_discount = (20 / nnz) ** topicality.TOPICALITY_DIVERSITY_PENALTY_GAMMA
    assert discounted == 5.0 / (length_discount * diversity_discount)


def test_score_topicality_emoji_spam_score_is_unchanged_by_length_discount():
    # 56ee036 fixed a real production bug where single-word/emoji posts like
    # this scored the theoretical max under L2 normalization. The length
    # discount must not disturb that fix: this text tokenizes to a single
    # token ("cute" -- the ellipsis and emoji don't match the vectorizer's
    # token pattern), so its score must come out mathematically identical to
    # the undiscounted formula -- not just "still low" relative to some other
    # post, which turns out not to be a stable property to assert (see
    # below).
    #
    # An earlier version of this test asserted the spam post scores below a
    # substantive one, using a small hand-built batch. That's not actually a
    # guarantee the shipped (pre-discount) formula makes either: in a small
    # corpus, singleton terms -- "cute" as much as any specific breakthrough
    # term -- tend toward the same IDF ceiling (verified empirically), so
    # that comparison is corpus-size-dependent, not a real invariant. The
    # single-token no-op property below is the actual guarantee this fix
    # relies on.
    spam_text = "cute... 😵‍💫"
    batch = [spam_text, "quantum entanglement breakthrough confirmed today"]

    new_score = topicality.compute_tfidf_scores(batch)[0]

    normalized = [topicality.normalize_text(t) for t in batch]
    vectorizer = topicality.TfidfVectorizer(stop_words="english", min_df=1, norm=None, sublinear_tf=True)
    matrix = vectorizer.fit_transform(normalized)
    old_score = float(np.mean(np.sort(matrix.getrow(0).data)[::-1][: topicality.TOPICALITY_TFIDF_TOP_K]))

    assert new_score == old_score


def test_score_topicality_length_parity_narrows_vs_undiscounted_formula():
    # Issue #23: Bluesky's shorter posts were structurally disadvantaged
    # because more terms give a post more chances to land a high-IDF term in
    # its top-3, independent of actual content quality. Reimplements the old
    # (pre-fix) undiscounted formula inline as a "before" comparator -- the
    # new formula's short/long score ratio should sit closer to 1.
    short_text = "quantum entanglement breakthrough confirmed today"
    long_text = (
        "quantum entanglement breakthrough confirmed today involving photons "
        "researchers laboratories physicists observatory telescope discovery"
    )
    texts = [short_text, long_text]

    new_scores = topicality.compute_tfidf_scores(texts)

    normalized = [topicality.normalize_text(t) for t in texts]
    vectorizer = topicality.TfidfVectorizer(stop_words="english", min_df=1, norm=None, sublinear_tf=True)
    matrix = vectorizer.fit_transform(normalized)
    old_scores = [
        float(np.mean(np.sort(matrix.getrow(i).data)[::-1][: topicality.TOPICALITY_TFIDF_TOP_K]))
        for i in range(matrix.shape[0])
    ]

    new_ratio = new_scores[0] / new_scores[1]
    old_ratio = old_scores[0] / old_scores[1]
    assert new_ratio > old_ratio


def test_compute_tfidf_scores_repetition_spam_does_not_beat_substantive_post():
    # issue #99: a post that repeats one non-stopword term many times used
    # to collapse to a single surviving TF-IDF entry and dodge the length
    # discount entirely, scoring above genuinely substantive posts. With the
    # discount keyed on actual token count, a long repetitive post is
    # discounted like any other long post.
    spam_text = "the best the best the best the best the best " * 2
    substantive_text = "quantum entanglement breakthrough confirmed by researchers today"
    scores = topicality.compute_tfidf_scores([spam_text, substantive_text])
    assert scores[0] < scores[1]


def test_score_topicality_splits_adjacent_camel_case_hashtags_into_separate_entities():
    # issue #70: score_topicality's NER call site applies split_camel_hashtags
    # (not the full normalize_text, which would lowercase and destroy the
    # case-boundary signal camelCase splitting depends on) before extraction.
    # Without it, adjacent glued hashtags confuse spaCy's NER into merging or
    # dropping entities -- confirmed here: the raw glued form only recovers
    # one of three names, while the split form recovers all three as
    # separate entities.
    index = InMemoryBurstIndex()
    post = FakePost(id=uuid4(), text="Great cast announcement #TomHanks #MerylStreep #DenzelWashington")
    result = topicality.score_topicality([post], index)[post.id]

    assert result.entities == ["tom hanks", "meryl streep", "denzel washington"]


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
    assert result.burst_component == 1 / topicality.TOPICALITY_BURST_THRESHOLD
    assert result.entities == ["nasa"]
    assert result.score > result.tfidf_component


class RaisingPipeline:
    def execute(self, command):
        return self

    def exec(self):
        raise RuntimeError("redis unreachable")


class RaisingClient:
    def pipeline(self):
        return RaisingPipeline()


def test_redis_burst_index_degrades_on_bump_entities_failure(monkeypatch):
    from infra import degradation, redis_client

    monkeypatch.setattr(redis_client, "get_client", lambda: RaisingClient())
    index = topicality.RedisBurstIndex()

    result = index.bump_entities([["earthquake", "california"], ["sourdough"]])

    assert result == [{}, {}]
    assert "topicality" in degradation.snapshot()
