import os
import re
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

import numpy as np
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer

from infra import degradation, redis_client
from util.text_normalize import normalize_text, split_camel_hashtags

# TF-IDF salience + entity-burst detection -- see the wiki's Topicality
# page for how this works and what each of these controls. Defaults are
# an empirically-validated configuration; treat any change as unvalidated
# until re-checked against a real production sample.
TOPICALITY_TFIDF_TOP_K = int(os.environ.get("TOPICALITY_TFIDF_TOP_K", "3"))
if TOPICALITY_TFIDF_TOP_K < 1:
    raise ValueError(f"TOPICALITY_TFIDF_TOP_K ({TOPICALITY_TFIDF_TOP_K}) must be at least 1")
TOPICALITY_LENGTH_NORM_ALPHA = float(os.environ.get("TOPICALITY_LENGTH_NORM_ALPHA", "0.3"))
# Separate from the length discount above: penalizes a post whose token
# count is large relative to its surviving distinct-term count -- i.e. text
# dominated by one or a few repeated words/stopwords rather than varied
# vocabulary. Validated against a random 4,000-post production sample
# (2026-08-26): real posts' token_count/nnz ratio maxes out around 14 even
# at the 99th percentile (median ~1.6), while a post degenerating to a
# single repeated term sits at 20+ -- genuinely outside the real
# distribution, unlike raw length, which many real posts share with such
# text. GAMMA=0.5 pushes that degenerate case to the bottom ~7% of the
# sample while leaving TOPICALITY_LENGTH_NORM_ALPHA's Bluesky/Mastodon
# parity (see that constant) essentially untouched (ratio 1.02 -> 0.99) --
# the two penalties are deliberately orthogonal, since a strong-enough pure
# length discount to suppress repetition would overshoot parity long before
# it suppressed the repetition itself. Re-validate before changing, same as
# TOPICALITY_LENGTH_NORM_ALPHA.
TOPICALITY_DIVERSITY_PENALTY_GAMMA = float(os.environ.get("TOPICALITY_DIVERSITY_PENALTY_GAMMA", "0.5"))
# An absolute floor on distinct-term count, orthogonal to the two ratio
# discounts above (which only bite on *repeated* words -- both collapse to
# 1.0 for a genuinely near-wordless post, where token_count == nnz). A post
# with fewer than this many surviving distinct terms has its topicality
# scaled by nnz / this, and is denied the entity-burst boost entirely: one
# or two rare tokens -- a bare hashtag, a link plus a word, an emoji string
# -- can't represent a topic no matter how batch-rare they are, and were
# otherwise scoring the batch *maximum* topicality. Validated at 3 against
# a production sample (2026-08-28): the nnz<=1 bucket is entirely
# vacuous/link-only, nnz==2 overwhelmingly so, and nnz>=3 (where ALPHA and
# the Bluesky/Mastodon parity live) is completely untouched (ramp == 1.0).
# Re-validate before changing, same as ALPHA/GAMMA.
TOPICALITY_MIN_DISTINCT_TERMS = int(os.environ.get("TOPICALITY_MIN_DISTINCT_TERMS", "3"))
if TOPICALITY_MIN_DISTINCT_TERMS < 1:
    raise ValueError(
        f"TOPICALITY_MIN_DISTINCT_TERMS ({TOPICALITY_MIN_DISTINCT_TERMS}) must be at least 1"
    )
TOPICALITY_BURST_THRESHOLD = int(os.environ.get("TOPICALITY_BURST_THRESHOLD", "5"))
if TOPICALITY_BURST_THRESHOLD < 1:
    raise ValueError(f"TOPICALITY_BURST_THRESHOLD ({TOPICALITY_BURST_THRESHOLD}) must be at least 1")
TOPICALITY_BURST_BOOST_WEIGHT = float(os.environ.get("TOPICALITY_BURST_BOOST_WEIGHT", "1.0"))
TOPICALITY_BURST_TTL_SECONDS = int(os.environ.get("TOPICALITY_BURST_TTL_SECONDS", str(3 * 60 * 60)))
# Caps the burst:entity:* Redis key name length -- entity text comes
# straight from spaCy NER with no upper bound otherwise. Doesn't affect
# the `entities` field persisted per post, only the burst-count key. See
# the wiki's Configuration: processing page's Redis capacity section.
TOPICALITY_ENTITY_KEY_MAX_LEN = int(os.environ.get("TOPICALITY_ENTITY_KEY_MAX_LEN", "100"))

# Entity types that plausibly signal a topic/newsworthy subject, not just
# calendar/quantity noise (DATE, CARDINAL, MONEY, PERCENT, etc. excluded
# by default). See the wiki's Topicality page for the full spaCy label set.
TOPICALITY_RELEVANT_ENTITY_LABELS = frozenset(
    v.strip()
    for v in os.environ.get(
        "TOPICALITY_RELEVANT_ENTITY_LABELS", "PERSON,ORG,GPE,LOC,FAC,EVENT,NORP,WORK_OF_ART"
    ).split(",")
    if v.strip()
)

_URL_ENTITY_RE = re.compile(r"^https?://\S+$")

_nlp: spacy.language.Language | None = None


def _get_nlp() -> spacy.language.Language:
    global _nlp
    if _nlp is None:
        # Only doc.ents is ever read (see extract_entities_typed below) - the
        # parser/tagger/attribute_ruler are independent pipeline components
        # that don't feed NER (they share tok2vec's embeddings, not each
        # other's output), so they run unconditionally on every post's text
        # for zero benefit unless disabled too.
        _nlp = spacy.load("en_core_web_sm", disable=["lemmatizer", "parser", "tagger", "attribute_ruler"])
    return _nlp


def _entities_from_doc(doc: spacy.tokens.Doc) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for ent in doc.ents:
        if ent.label_ not in TOPICALITY_RELEVANT_ENTITY_LABELS:
            continue
        normalized = ent.text.strip().lower()
        # spaCy's NER occasionally mis-tags a URL span as a relevant label
        # (ORG/GPE are the ones seen in practice) -- a URL is never a
        # meaningful "topicality entity".
        if normalized and normalized not in seen and not _URL_ENTITY_RE.match(normalized):
            seen[normalized] = ent.label_
    return list(seen.items())


def extract_entities_typed_batch(texts: list[str]) -> list[list[tuple[str, str]]]:
    """(entity text, spaCy label) pairs per text, deduped within each text
    (first-seen label wins). Runs the whole batch through nlp.pipe() in one
    call rather than once per text -- score_topicality uses this, not the
    single-text extract_entities_typed below, for exactly that reason. See
    the wiki's Topicality page."""
    return [_entities_from_doc(doc) for doc in _get_nlp().pipe(texts)]


def extract_entities_typed(text: str) -> list[tuple[str, str]]:
    """Single-text convenience wrapper around extract_entities_typed_batch --
    see there for the batch-processing path score_topicality actually uses.
    The typed form everything else is built on -- extract_entities() below
    just strips the label for callers that only need text."""
    return extract_entities_typed_batch([text])[0]


def extract_entities(text: str) -> list[str]:
    return [entity_text for entity_text, _label in extract_entities_typed(text)]


def extract_entities_batch(texts: list[str]) -> list[list[str]]:
    return [
        [entity_text for entity_text, _label in typed] for typed in extract_entities_typed_batch(texts)
    ]


def _top_k_mean(values: np.ndarray, k: int, token_count: int) -> float:
    """Doubly-discounted mean of a doc's top-k TF-IDF weights -- see the
    wiki's Topicality page for why each discount exists and how its
    constant was chosen.

    Two independent discounts, both keyed on token_count (every token the
    vectorizer's own tokenizer matched, including stopwords and repeats) vs.
    values.size/nnz (the count of distinct terms that survived stopword
    filtering into a nonzero TF-IDF weight):

    - Length (TOPICALITY_LENGTH_NORM_ALPHA): divides by token_count itself,
      so a post with more text overall isn't structurally favored just for
      having more chances at a high-IDF term.
    - Diversity (TOPICALITY_DIVERSITY_PENALTY_GAMMA): divides further by
      token_count/nnz, the ratio of total tokens to distinct surviving
      terms -- large when a post is dominated by one or a few repeated
      words/stopwords rather than varied vocabulary. This is what actually
      catches a post that repeats one non-stopword term many times: nnz
      collapses to 1 same as a genuinely short post would, but token_count
      stays large, so the ratio -- and the discount -- stays large too.

    Neither ratio discount touches a genuinely near-wordless post:
    token_count == nnz there, so both collapse to 1 (`1 ** x == 1`). That
    left a one- or two-distinct-term post (a bare hashtag, a link plus a
    word) carrying its full batch-relative IDF -- often the batch maximum.
    TOPICALITY_MIN_DISTINCT_TERMS closes that with an absolute ramp: the
    result is scaled by min(1, nnz / K), so nnz below K is attenuated in
    proportion to how few distinct terms survived, and nnz >= K is
    unaffected."""
    if values.size == 0:
        return 0.0
    top = np.sort(values)[::-1][:k]
    raw_mean = float(np.mean(top))
    token_count = max(token_count, 1)
    nnz = values.size
    length_discount = token_count**TOPICALITY_LENGTH_NORM_ALPHA
    diversity_discount = (token_count / nnz) ** TOPICALITY_DIVERSITY_PENALTY_GAMMA
    distinct_term_ramp = min(1.0, nnz / TOPICALITY_MIN_DISTINCT_TERMS)
    return raw_mean / (length_discount * diversity_discount) * distinct_term_ramp


def _top_k_terms(indices: np.ndarray, values: np.ndarray, feature_names: np.ndarray, k: int) -> list[str]:
    if values.size == 0:
        return []
    order = np.argsort(values)[::-1][:k]
    return [str(feature_names[indices[i]]) for i in order]


def _compute_tfidf(texts: list[str]) -> tuple[list[float], list[list[str]], list[int]]:
    """Single fit shared by compute_tfidf_scores (score only) and
    score_topicality (score + the actual top-K term strings, which
    taxonomy.categorize() matches against for rule-based categorization,
    + each doc's nnz, which score_topicality gates the burst boost on) --
    fitting TfidfVectorizer twice per cycle for the same batch would be
    pure waste."""
    normalized = [normalize_text(t) for t in texts]
    try:
        # norm=None/sublinear_tf/no max_df -- deliberate deviations from
        # TfidfVectorizer's defaults. See the wiki's Topicality page for why
        # each one matters here.
        vectorizer = TfidfVectorizer(stop_words="english", min_df=1, norm=None, sublinear_tf=True)
        matrix = vectorizer.fit_transform(normalized)
    except ValueError:
        # empty vocabulary — e.g. a tiny batch that's all stopwords/URLs
        return [0.0] * len(texts), [[] for _ in texts], [0] * len(texts)

    feature_names = vectorizer.get_feature_names_out()
    # Reuses the vectorizer's own token_pattern (not a hand-rolled regex) so
    # the length proxy _top_k_mean discounts by can never silently diverge
    # from what TF-IDF itself tokenized. build_tokenizer() only applies
    # token_pattern, not stop_words filtering, so this counts every token
    # including stopwords and repeats -- see _top_k_mean's docstring.
    tokenizer = vectorizer.build_tokenizer()
    scores: list[float] = []
    top_terms: list[list[str]] = []
    nnzs: list[int] = []
    for i in range(matrix.shape[0]):
        row = matrix.getrow(i)
        token_count = len(tokenizer(normalized[i]))
        scores.append(_top_k_mean(row.data, TOPICALITY_TFIDF_TOP_K, token_count))
        top_terms.append(_top_k_terms(row.indices, row.data, feature_names, TOPICALITY_TFIDF_TOP_K))
        nnzs.append(int(row.data.size))
    return scores, top_terms, nnzs


def compute_tfidf_scores(texts: list[str]) -> list[float]:
    """Per-document salience: the mean of each doc's top-K TF-IDF weights,
    so a post is scored by its most distinctive terms rather than diluted
    by its length."""
    return _compute_tfidf(texts)[0]  # scores only; top_terms/nnz are for score_topicality


class BurstIndex(Protocol):
    def bump_entities(self, entities_by_post: list[list[str]]) -> list[dict[str, int]]: ...


class RedisBurstIndex:
    """Recent entity-mention counts, in Redis. Short TTL by design —
    this is a "spiking right now" signal, not a durable count. See the
    wiki's Topicality page."""

    def __init__(self) -> None:
        self.client = redis_client.get_client()

    def bump_entities(self, entities_by_post: list[list[str]]) -> list[dict[str, int]]:
        """One pipelined round trip for every post's entity bumps in the
        batch, not one round trip per post -- Redis executes a pipeline's
        commands strictly in order, so this produces the exact same
        per-post counts as bumping post by post, just faster. See the
        wiki's Topicality page."""
        flat_entities = [entity for entities in entities_by_post for entity in entities]
        if not flat_entities:
            return [{} for _ in entities_by_post]

        try:
            pipe = self.client.pipeline()
            for entity in flat_entities:
                key = f"burst:entity:{entity[:TOPICALITY_ENTITY_KEY_MAX_LEN]}"
                pipe.incr(key)
                pipe.expire(key, TOPICALITY_BURST_TTL_SECONDS)
            results = pipe.exec()
        except Exception as exc:
            # Degrades to the same shape this function already returns for
            # "no entities at all" -- every post's burst_component becomes 0
            # for the batch, so score just falls back to plain
            # tfidf_component. A pure ranking-input weakening, no false
            # signal in either direction. See the wiki's Topicality page.
            degradation.record("topicality", str(exc))
            return [{} for _ in entities_by_post]

        degradation.clear("topicality")
        counts_flat = results[0::2]  # incr, expire, incr, expire, ...

        counts_by_post: list[dict[str, int]] = []
        i = 0
        for entities in entities_by_post:
            counts_by_post.append({entity: counts_flat[i + j] for j, entity in enumerate(entities)})
            i += len(entities)
        return counts_by_post


@dataclass
class TopicalityResult:
    score: float
    entities: list[str] = field(default_factory=list)
    tfidf_component: float = 0.0
    burst_component: float = 0.0
    top_terms: list[str] = field(default_factory=list)


def score_topicality(posts: list, index: BurstIndex) -> dict[UUID, TopicalityResult]:
    """Combines within-batch TF-IDF salience with a cross-cycle entity-burst
    signal: posts mentioning entities that are currently spiking (per Redis)
    get their TF-IDF score upweighted, since burst is what actually captures
    "trending now" — TF-IDF alone only measures rarity within a single
    batch, which isn't the same thing. Both the spaCy NER pass and the
    Redis burst-bump run once for the whole batch, not once per post. See
    the wiki's Topicality page."""
    texts = [post.text for post in posts]
    tfidf_scores, tfidf_top_terms, tfidf_nnzs = _compute_tfidf(texts)
    # split_camel_hashtags only, not normalize_text -- NER needs original
    # casing, which normalize_text() lowercases away. _compute_tfidf above
    # already gets this via its own normalize_text() call.
    entities_by_post = extract_entities_batch([split_camel_hashtags(t) for t in texts])
    entity_counts_by_post = index.bump_entities(entities_by_post)

    results: dict[UUID, TopicalityResult] = {}
    for post, tfidf_component, top_terms, nnz, entities, entity_counts in zip(
        posts, tfidf_scores, tfidf_top_terms, tfidf_nnzs, entities_by_post, entity_counts_by_post
    ):
        max_count = max(entity_counts.values(), default=0)
        burst_component = min(1.0, max_count / TOPICALITY_BURST_THRESHOLD)
        # A near-wordless post can't be "trending on a topic" -- it has no
        # topic, just one or two rare tokens. Deny it the burst boost
        # entirely (the nnz ramp in _top_k_mean has already attenuated its
        # tfidf_component). See TOPICALITY_MIN_DISTINCT_TERMS.
        if nnz < TOPICALITY_MIN_DISTINCT_TERMS:
            burst_component = 0.0

        score = tfidf_component * (1.0 + TOPICALITY_BURST_BOOST_WEIGHT * burst_component)

        results[post.id] = TopicalityResult(
            score=score,
            entities=entities,
            tfidf_component=tfidf_component,
            burst_component=burst_component,
            top_terms=top_terms,
        )

    return results
