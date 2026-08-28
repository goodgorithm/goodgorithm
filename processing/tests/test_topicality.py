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
    _, top_terms, _ = topicality._compute_tfidf(texts)
    assert len(top_terms) == 2
    assert all(isinstance(term, str) for term in top_terms[0])
    assert set(top_terms[0]).issubset(set(texts[0].split()))
    assert set(top_terms[1]).issubset(set(texts[1].split()))


def test_compute_tfidf_top_terms_empty_for_empty_vocabulary_batch():
    texts = ["the the the", "a a a"]
    _, top_terms, nnzs = topicality._compute_tfidf(texts)
    assert top_terms == [[], []]
    assert nnzs == [0, 0]


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


def test_score_topicality_burst_boost_applies_only_above_the_distinct_term_floor():
    # issue #118: the same spiking entity appears in both posts, but only the
    # one with enough distinct vocabulary to actually be *about* a topic gets
    # the boost. A near-wordless post riding a trend is pure trend-surfing --
    # burst_component is forced to 0 even though "nasa" is spiking.
    index = InMemoryBurstIndex()
    for _ in range(topicality.TOPICALITY_BURST_THRESHOLD):
        index.bump_entities([["nasa"]])

    near_wordless = FakePost(id=uuid4(), text="NASA rocks")  # 2 distinct terms
    substantive = FakePost(
        id=uuid4(), text="Scientists at NASA confirmed the new mission timeline today"
    )
    results = topicality.score_topicality([near_wordless, substantive], index)

    assert results[near_wordless.id].entities == ["nasa"]  # entity was recognized
    assert results[near_wordless.id].burst_component == 0.0
    assert results[near_wordless.id].score == results[near_wordless.id].tfidf_component
    assert results[substantive.id].burst_component == 1.0
    assert results[substantive.id].score > results[substantive.id].tfidf_component


def test_top_k_mean_single_distinct_term_is_ramped_down():
    # issue #118: a post with one surviving distinct term (a bare hashtag, a
    # link plus a word) used to keep its full batch-relative weight -- both
    # ratio discounts collapse to 1 when token_count == nnz -- and routinely
    # scored the batch *maximum* topicality. The absolute distinct-term ramp
    # scales it by nnz / TOPICALITY_MIN_DISTINCT_TERMS. (norm=None already
    # caps the earlier L2-inflation regression, 56ee036; this is a separate
    # layer on top.)
    ramp = 1 / topicality.TOPICALITY_MIN_DISTINCT_TERMS
    assert topicality._top_k_mean(np.array([1.0]), 3, token_count=1) == 1.0 * ramp


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
    # nnz == 3 sits at (default) TOPICALITY_MIN_DISTINCT_TERMS, so the #118
    # distinct-term ramp is exactly 1 here and doesn't enter into it.
    assert with_diversity == length_only


def test_top_k_mean_ramps_down_below_the_distinct_term_floor():
    # issue #118: hold token_count == nnz so both ratio discounts stay fixed
    # at 1 and the only thing moving is the absolute ramp -- linear in nnz
    # below TOPICALITY_MIN_DISTINCT_TERMS, exactly 1 at or above it.
    floor = topicality.TOPICALITY_MIN_DISTINCT_TERMS
    k = topicality.TOPICALITY_TFIDF_TOP_K

    def result_and_baseline(nnz):
        values = np.array([3.0] * nnz)
        got = topicality._top_k_mean(values, k, token_count=nnz)
        raw_mean = float(np.mean(np.sort(values)[::-1][:k]))
        baseline = raw_mean / (nnz**topicality.TOPICALITY_LENGTH_NORM_ALPHA)
        return got, baseline

    for nnz in range(1, floor):
        got, baseline = result_and_baseline(nnz)
        assert got == baseline * (nnz / floor)

    for nnz in (floor, floor + 3):
        got, baseline = result_and_baseline(nnz)
        assert got == baseline


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
    # nnz == 1 also puts this below the #118 distinct-term floor, so the ramp
    # (min(1, nnz / TOPICALITY_MIN_DISTINCT_TERMS)) is a third factor now --
    # the diversity discount is still what separates this from a genuine
    # single-term post.
    distinct_term_ramp = min(1.0, nnz / topicality.TOPICALITY_MIN_DISTINCT_TERMS)
    assert discounted == 5.0 / (length_discount * diversity_discount) * distinct_term_ramp


def test_score_topicality_single_token_emoji_spam_is_ramped_down():
    # 56ee036 + norm=None keep single-word/emoji posts like this off the L2
    # ceiling they once hit. issue #118 adds the layer this test now covers:
    # "cute..." tokenizes to a single term (the ellipsis and emoji don't
    # match the vectorizer's token pattern), so it has nnz == 1 and is scaled
    # by min(1, nnz / TOPICALITY_MIN_DISTINCT_TERMS) -- it can no longer sit
    # at the same salience as a multi-term substantive post.
    spam_text = "cute... 😵‍💫"
    batch = [spam_text, "quantum entanglement breakthrough confirmed today"]

    new_score = topicality.compute_tfidf_scores(batch)[0]

    normalized = [topicality.normalize_text(t) for t in batch]
    vectorizer = topicality.TfidfVectorizer(stop_words="english", min_df=1, norm=None, sublinear_tf=True)
    matrix = vectorizer.fit_transform(normalized)
    row = matrix.getrow(0)
    token_count = len(vectorizer.build_tokenizer()(normalized[0]))
    undiscounted = float(np.mean(np.sort(row.data)[::-1][: topicality.TOPICALITY_TFIDF_TOP_K]))
    ramp = min(1.0, row.data.size / topicality.TOPICALITY_MIN_DISTINCT_TERMS)

    assert row.data.size == 1 and token_count == 1  # premise: one term, one token
    assert ramp < 1.0
    assert new_score == undiscounted * ramp
    assert new_score < undiscounted


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
