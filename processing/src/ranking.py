from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from dedup import normalize_text

POSITIVITY_THRESHOLD = 0.3  # eligibility bar — only clearly-positive posts rank at all
HALF_LIFE_HOURS = 12.0  # a post's recency weight halves every 12h
MMR_WINDOW_HOURS = 72.0  # ranking pool bound — also keeps MMR's O(n^2) pass cheap
MMR_LAMBDA = 0.7  # weight on relevance (base_score) vs diversity penalty
SIMILARITY_TFIDF_WEIGHT = 0.5
SIMILARITY_ENTITY_WEIGHT = 0.5


@dataclass
class RankablePost:
    id: UUID
    text: str
    created_at: datetime
    sentiment_score: float
    topicality_score: float
    entities: list[str]
    is_bot: bool
    is_dedup_canonical: bool


@dataclass
class RankResult:
    base_score: float
    rank_score: float
    rank_position: int  # 0-indexed selection order from the MMR pass


def positivity(sentiment_score: float) -> float:
    return max(0.0, sentiment_score)


MIN_DECAY = 1e-30  # comfortably above float4/REAL's underflow range (~1.4e-45)


def recency_decay(created_at: datetime, now: datetime) -> float:
    """run_cycle() computes base_score for every fetched post unconditionally
    (the 72h MMR window is only applied later, in rank_posts), so this has to
    handle arbitrarily old posts — e.g. backlog/boosted content ingestion can
    surface that's genuinely months old. 0.5 ** (age_hours / HALF_LIFE_HOURS)
    for a post that old is still a valid nonzero Python float (float64 has a
    much wider range), but is too small for Postgres's REAL (float4) column
    to store, raising `NumericValueOutOfRange: underflow` on write. Snap
    anything below float4's range to exactly 0.0, which is both safely
    representable and the semantically correct value for "no recency weight
    left" anyway."""
    age_hours = max(0.0, (now - created_at).total_seconds() / 3600.0)
    decay = 0.5 ** (age_hours / HALF_LIFE_HOURS)
    return decay if decay >= MIN_DECAY else 0.0


def compute_base_score(post: RankablePost, now: datetime) -> float:
    """Content-derived only — positivity x topicality x recency. No
    engagement field exists on RankablePost for this to accidentally read."""
    return positivity(post.sentiment_score) * post.topicality_score * recency_decay(post.created_at, now)


def filter_eligible(posts: list[RankablePost]) -> list[RankablePost]:
    return [
        p
        for p in posts
        if not p.is_bot and p.is_dedup_canonical and p.sentiment_score >= POSITIVITY_THRESHOLD
    ]


def _entity_jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _similarity_matrix(posts: list[RankablePost]) -> np.ndarray:
    n = len(posts)
    if n == 0:
        return np.zeros((0, 0))

    texts = [normalize_text(p.text) for p in posts]
    try:
        vectorizer = TfidfVectorizer(stop_words="english", min_df=1)
        tfidf_matrix = vectorizer.fit_transform(texts)
        tfidf_sim = cosine_similarity(tfidf_matrix)
    except ValueError:
        tfidf_sim = np.zeros((n, n))

    entity_sets = [set(p.entities) for p in posts]
    entity_sim = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            sim = _entity_jaccard(entity_sets[i], entity_sets[j])
            entity_sim[i, j] = sim
            entity_sim[j, i] = sim

    return SIMILARITY_TFIDF_WEIGHT * tfidf_sim + SIMILARITY_ENTITY_WEIGHT * entity_sim


def rank_posts(posts: list[RankablePost], now: datetime | None = None) -> dict[UUID, RankResult]:
    """Filters to eligible posts within a recent window, computes a content-
    derived base_score (positivity x topicality x recency), then greedily
    selects posts by Maximal Marginal Relevance so near-duplicate topics
    don't dominate the feed. Selection order becomes rank_score — provably
    non-increasing across rounds (each round's winner is bounded by the
    previous round's max), so `ORDER BY rank_score DESC` in the API
    reproduces this exact order."""
    if now is None:
        now = datetime.now(timezone.utc)

    eligible = filter_eligible(posts)
    cutoff = now - timedelta(hours=MMR_WINDOW_HOURS)
    windowed = [p for p in eligible if p.created_at >= cutoff]

    results: dict[UUID, RankResult] = {}
    if not windowed:
        return results

    base_scores = {p.id: compute_base_score(p, now) for p in windowed}
    sim_matrix = _similarity_matrix(windowed)

    remaining = set(range(len(windowed)))
    selected: list[int] = []

    while remaining:
        best_idx: int | None = None
        best_mmr: float | None = None
        for i in remaining:
            max_sim = max((sim_matrix[i, j] for j in selected), default=0.0)
            mmr = MMR_LAMBDA * base_scores[windowed[i].id] - (1 - MMR_LAMBDA) * max_sim
            if best_mmr is None or mmr > best_mmr:
                best_mmr = mmr
                best_idx = i

        selected.append(best_idx)
        remaining.discard(best_idx)
        post = windowed[best_idx]
        results[post.id] = RankResult(
            base_score=base_scores[post.id],
            rank_score=best_mmr,
            rank_position=len(selected) - 1,
        )

    return results
