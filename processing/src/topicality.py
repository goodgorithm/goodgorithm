from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

import numpy as np
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer

import redis_client
from dedup import normalize_text

TFIDF_TOP_K = 3
BURST_THRESHOLD = 5  # mentions within the window to reach a "fully bursting" entity
BURST_BOOST_WEIGHT = 1.0  # a fully-bursting entity can double a post's topicality score
BURST_TTL_SECONDS = 3 * 60 * 60  # 3 hours — "spiking now", not a durable count
# Caps the burst:entity:* Redis key name length. Entity text comes straight
# from spaCy NER (WORK_OF_ART/ORG/EVENT labels can be long multi-word
# phrases) with no upper bound otherwise -- an unbounded-cardinality,
# unbounded-length key pattern (2026-08-12 Redis capacity review). Doesn't
# affect the `entities` field persisted per post, only the burst-count key.
ENTITY_KEY_MAX_LEN = 100

# Entity types that plausibly signal a topic/newsworthy subject, not just
# calendar/quantity noise (DATE, CARDINAL, MONEY, PERCENT, etc. excluded).
RELEVANT_ENTITY_LABELS = {"PERSON", "ORG", "GPE", "LOC", "FAC", "EVENT", "NORP", "WORK_OF_ART"}

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
    below just strips the label for callers that only need text, and
    taxonomy.categorize() uses RELEVANT_ENTITY_LABELS-filtered entity text
    the same way (see pipeline.py) rather than re-checking type at that
    layer -- the filtering already happened here."""
    doc = _get_nlp()(text)
    seen: dict[str, str] = {}
    for ent in doc.ents:
        if ent.label_ not in RELEVANT_ENTITY_LABELS:
            continue
        normalized = ent.text.strip().lower()
        if normalized and normalized not in seen:
            seen[normalized] = ent.label_
    return list(seen.items())


def extract_entities(text: str) -> list[str]:
    return [entity_text for entity_text, _label in extract_entities_typed(text)]


def _top_k_mean(values: np.ndarray, k: int) -> float:
    if values.size == 0:
        return 0.0
    top = np.sort(values)[::-1][:k]
    return float(np.mean(top))


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
        # norm=None: sklearn's default L2 row-normalization concentrates a
        # short doc's entire weight onto its handful of terms (a 1-term doc
        # gets that term at weight 1.0), which made single-word/emoji posts
        # systematically outscore substantive ones. Raw (unnormalized)
        # weights compare terms by genuine corpus-wide rarity instead of
        # doc sparsity. sublinear_tf dampens repeated-word spam within a doc.
        #
        # no max_df cutoff: every term is "100% of the batch" when the batch
        # is small (even a single post), so a <1.0 cutoff can silently drop
        # the entire vocabulary on quiet cycles. English stopword removal
        # already handles the truly generic filler words.
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
        scores.append(_top_k_mean(row.data, TFIDF_TOP_K))
        top_terms.append(_top_k_terms(row.indices, row.data, feature_names, TFIDF_TOP_K))
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
    this is a "spiking right now" signal, not a durable count."""

    def __init__(self) -> None:
        self.client = redis_client.get_client()

    def bump_entities(self, entities: list[str]) -> dict[str, int]:
        if not entities:
            return {}
        pipe = self.client.pipeline()
        for entity in entities:
            key = f"burst:entity:{entity[:ENTITY_KEY_MAX_LEN]}"
            pipe.incr(key)
            pipe.expire(key, BURST_TTL_SECONDS)
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
    batch, which isn't the same thing."""
    tfidf_scores, tfidf_top_terms = _compute_tfidf([post.text for post in posts])

    results: dict[UUID, TopicalityResult] = {}
    for post, tfidf_component, top_terms in zip(posts, tfidf_scores, tfidf_top_terms):
        entities = extract_entities(post.text)
        entity_counts = index.bump_entities(entities)
        max_count = max(entity_counts.values(), default=0)
        burst_component = min(1.0, max_count / BURST_THRESHOLD)

        score = tfidf_component * (1.0 + BURST_BOOST_WEIGHT * burst_component)

        results[post.id] = TopicalityResult(
            score=score,
            entities=entities,
            tfidf_component=tfidf_component,
            burst_component=burst_component,
            top_terms=top_terms,
        )

    return results
