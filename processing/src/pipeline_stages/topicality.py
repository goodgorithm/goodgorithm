import os
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

import numpy as np
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer

from infra import redis_client
from text_normalize import normalize_text

# TF-IDF salience + entity-burst detection -- see the wiki's Topicality
# page for how this works and what each of these controls. Defaults are
# an empirically-validated configuration; treat any change as unvalidated
# until re-checked against a real production sample.
TOPICALITY_TFIDF_TOP_K = int(os.environ.get("TOPICALITY_TFIDF_TOP_K", "3"))
if TOPICALITY_TFIDF_TOP_K < 1:
    raise ValueError(f"TOPICALITY_TFIDF_TOP_K ({TOPICALITY_TFIDF_TOP_K}) must be at least 1")
TOPICALITY_LENGTH_NORM_ALPHA = float(os.environ.get("TOPICALITY_LENGTH_NORM_ALPHA", "0.3"))
TOPICALITY_BURST_THRESHOLD = int(os.environ.get("TOPICALITY_BURST_THRESHOLD", "5"))
if TOPICALITY_BURST_THRESHOLD < 1:
    raise ValueError(f"TOPICALITY_BURST_THRESHOLD ({TOPICALITY_BURST_THRESHOLD}) must be at least 1")
TOPICALITY_BURST_BOOST_WEIGHT = float(os.environ.get("TOPICALITY_BURST_BOOST_WEIGHT", "1.0"))
TOPICALITY_BURST_TTL_SECONDS = int(os.environ.get("TOPICALITY_BURST_TTL_SECONDS", str(3 * 60 * 60)))
# Caps the burst:entity:* Redis key name length -- entity text comes
# straight from spaCy NER with no upper bound otherwise. Doesn't affect
# the `entities` field persisted per post, only the burst-count key. See
# the wiki's Configuration page's Redis capacity section.
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


def extract_entities_typed(text: str) -> list[tuple[str, str]]:
    """(entity text, spaCy label) pairs, deduped by text (first-seen label
    wins). The typed form everything else is built on -- extract_entities()
    below just strips the label for callers that only need text. See the
    wiki's Topicality page."""
    doc = _get_nlp()(text)
    seen: dict[str, str] = {}
    for ent in doc.ents:
        if ent.label_ not in TOPICALITY_RELEVANT_ENTITY_LABELS:
            continue
        normalized = ent.text.strip().lower()
        if normalized and normalized not in seen:
            seen[normalized] = ent.label_
    return list(seen.items())


def extract_entities(text: str) -> list[str]:
    return [entity_text for entity_text, _label in extract_entities_typed(text)]


def _top_k_mean(values: np.ndarray, k: int) -> float:
    """Length-discounted mean of a doc's top-k TF-IDF weights -- see the
    wiki's Topicality page for why the discount exists and how
    TOPICALITY_LENGTH_NORM_ALPHA was chosen."""
    if values.size == 0:
        return 0.0
    top = np.sort(values)[::-1][:k]
    raw_mean = float(np.mean(top))
    return raw_mean / (values.size**TOPICALITY_LENGTH_NORM_ALPHA)


def _top_k_terms(indices: np.ndarray, values: np.ndarray, feature_names: np.ndarray, k: int) -> list[str]:
    if values.size == 0:
        return []
    order = np.argsort(values)[::-1][:k]
    return [str(feature_names[indices[i]]) for i in order]


def _compute_tfidf(texts: list[str]) -> tuple[list[float], list[list[str]]]:
    """Single fit shared by compute_tfidf_scores (score only) and
    score_topicality (score + the actual top-K term strings, which
    taxonomy.categorize() matches against for rule-based categorization) --
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
        return [0.0] * len(texts), [[] for _ in texts]

    feature_names = vectorizer.get_feature_names_out()
    scores: list[float] = []
    top_terms: list[list[str]] = []
    for i in range(matrix.shape[0]):
        row = matrix.getrow(i)
        scores.append(_top_k_mean(row.data, TOPICALITY_TFIDF_TOP_K))
        top_terms.append(_top_k_terms(row.indices, row.data, feature_names, TOPICALITY_TFIDF_TOP_K))
    return scores, top_terms


def compute_tfidf_scores(texts: list[str]) -> list[float]:
    """Per-document salience: the mean of each doc's top-K TF-IDF weights,
    so a post is scored by its most distinctive terms rather than diluted
    by its length."""
    return _compute_tfidf(texts)[0]


class BurstIndex(Protocol):
    def bump_entities(self, entities: list[str]) -> dict[str, int]: ...


class RedisBurstIndex:
    """Recent entity-mention counts, in Upstash Redis. Short TTL by design —
    this is a "spiking right now" signal, not a durable count. See the
    wiki's Topicality page."""

    def __init__(self) -> None:
        self.client = redis_client.get_client()

    def bump_entities(self, entities: list[str]) -> dict[str, int]:
        if not entities:
            return {}
        pipe = self.client.pipeline()
        for entity in entities:
            key = f"burst:entity:{entity[:TOPICALITY_ENTITY_KEY_MAX_LEN]}"
            pipe.incr(key)
            pipe.expire(key, TOPICALITY_BURST_TTL_SECONDS)
        results = pipe.exec()
        counts = results[0::2]  # incr, expire, incr, expire, ...
        return dict(zip(entities, counts))


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
    batch, which isn't the same thing. See the wiki's Topicality page."""
    tfidf_scores, tfidf_top_terms = _compute_tfidf([post.text for post in posts])

    results: dict[UUID, TopicalityResult] = {}
    for post, tfidf_component, top_terms in zip(posts, tfidf_scores, tfidf_top_terms):
        entities = extract_entities(post.text)
        entity_counts = index.bump_entities(entities)
        max_count = max(entity_counts.values(), default=0)
        burst_component = min(1.0, max_count / TOPICALITY_BURST_THRESHOLD)

        score = tfidf_component * (1.0 + TOPICALITY_BURST_BOOST_WEIGHT * burst_component)

        results[post.id] = TopicalityResult(
            score=score,
            entities=entities,
            tfidf_component=tfidf_component,
            burst_component=burst_component,
            top_terms=top_terms,
        )

    return results
