from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from text_normalize import normalize_text

POSITIVITY_THRESHOLD = 0.3  # eligibility bar — only clearly-positive posts rank at all
HALF_LIFE_HOURS = 12.0  # a post's recency weight halves every 12h
MMR_WINDOW_HOURS = 72.0  # ranking pool bound — also keeps MMR's O(n^2) pass cheap
MMR_CANDIDATE_POOL_SIZE = 2000  # hard cap on MMR's O(n^2) *memory* — see rank_posts
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
    # context_dependency.py's per-platform devalue multiplier (issue #33) --
    # 1.0 for posts that aren't context-dependent (or whose platform's
    # policy is exclude-only, so a devalued post never reaches ranking at
    # all). Content-derived, same category as topicality/sentiment, not an
    # engagement signal.
    context_penalty: float = 1.0


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
    """Content-derived only — positivity x topicality x recency x
    context_penalty. No engagement field exists on RankablePost for this to
    accidentally read."""
    return (
        positivity(post.sentiment_score)
        * post.topicality_score
        * recency_decay(post.created_at, now)
        * post.context_penalty
    )


def filter_eligible(posts: list[RankablePost]) -> list[RankablePost]:
    return [
        p
        for p in posts
        if not p.is_bot and p.is_dedup_canonical and p.sentiment_score >= POSITIVITY_THRESHOLD
    ]


def _entity_similarity_matrix(entity_lists: list[list[str]]) -> np.ndarray:
    """Pairwise Jaccard similarity for n sets, vectorized. A pure-Python
    double loop here is O(n^2) *Python-level* work (set ops + function calls
    per pair) - fine for a handful of posts, but at real production volume
    (thousands of eligible posts in the MMR window) it's tens of millions of
    interpreted operations per cycle, slow and memory-hungry enough to crash
    the process outright (confirmed 2026-08-09: silently OOM-killed every
    cycle once the window hit ~5,200 eligible posts, no traceback since a
    kill -9 gives Python no chance to log one).

    Same math (intersection/union), done as one sparse matrix multiply
    instead: build an n x |vocab| binary "post mentions entity" matrix M;
    M @ M.T gives pairwise intersection counts in a single (C-level) sparse
    matmul, and union follows from each set's own size via broadcasting.
    """
    n = len(entity_lists)
    if n == 0:
        return np.zeros((0, 0))

    vocab: dict[str, int] = {}
    rows: list[int] = []
    cols: list[int] = []
    for i, entities in enumerate(entity_lists):
        for entity in set(entities):
            col = vocab.setdefault(entity, len(vocab))
            rows.append(i)
            cols.append(col)

    if not vocab:
        return np.zeros((n, n))

    membership = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, len(vocab)))
    intersection = (membership @ membership.T).toarray()
    sizes = np.asarray(membership.sum(axis=1)).ravel()
    union = sizes[:, None] + sizes[None, :] - intersection

    with np.errstate(divide="ignore", invalid="ignore"):
        jaccard = np.where(union > 0, intersection / union, 0.0)
    np.fill_diagonal(jaccard, 0.0)  # self-similarity is never consulted, but keep it clean
    return jaccard


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

    entity_sim = _entity_similarity_matrix([p.entities for p in posts])

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

    # MMR_WINDOW_HOURS bounds the pool by time, not size — under real
    # ingestion volume it's held 5k-30k+ eligible posts and kept growing
    # (confirmed in production 2026-08-09). ea4fcb6 vectorized the O(n^2)
    # *compute* here (cosine_similarity + the entity Jaccard matmul), but
    # both still materialize dense n x n float64 arrays: at n=29,770 a
    # single one is ~7GB, and _similarity_matrix builds three of them
    # (tfidf_sim, entity_sim, the combined result) against a 1GB container
    # limit — an OOM kill regardless of how fast the vectorized math runs.
    # A feed only ever surfaces a bounded slice anyway, so cap the pool to
    # the top candidates by base_score before the O(n^2) pass — same idea
    # as the time-based window, just a size-based one. Self-correcting:
    # the pool is reselected fresh every cycle, so a post that misses the
    # cut can still enter later once higher-scoring posts decay past it.
    if len(windowed) > MMR_CANDIDATE_POOL_SIZE:
        windowed = sorted(windowed, key=lambda p: base_scores[p.id], reverse=True)[:MMR_CANDIDATE_POOL_SIZE]

    sim_matrix = _similarity_matrix(windowed)

    # Same greedy MMR as before (each round still needs the *current* best
    # remaining candidate given everything already selected, which is
    # inherently sequential), but tracked with a running per-post "max
    # similarity to anything selected so far" vector instead of
    # recomputing max(sim_matrix[i, j] for j in selected) from scratch for
    # every remaining i on every round - that was the second O(n^2)
    # pure-Python hot spot alongside the entity-similarity loop, same
    # production crash (see _entity_similarity_matrix).
    n = len(windowed)
    base_scores_arr = np.array([base_scores[p.id] for p in windowed])
    max_sim_to_selected = np.zeros(n)
    remaining_mask = np.ones(n, dtype=bool)

    for rank_position in range(n):
        mmr_values = MMR_LAMBDA * base_scores_arr - (1 - MMR_LAMBDA) * max_sim_to_selected
        mmr_values = np.where(remaining_mask, mmr_values, -np.inf)
        best_idx = int(np.argmax(mmr_values))

        post = windowed[best_idx]
        results[post.id] = RankResult(
            base_score=base_scores[post.id],
            rank_score=float(mmr_values[best_idx]),
            rank_position=rank_position,
        )

        remaining_mask[best_idx] = False
        max_sim_to_selected = np.maximum(max_sim_to_selected, sim_matrix[:, best_idx])

    return results
