import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from pipeline_stages import bot_filter
from util.text_normalize import normalize_text

# See the wiki's Ranking page for what each of these controls and why the
# defaults are what they are.
RANKING_POSITIVITY_THRESHOLD = float(os.environ.get("RANKING_POSITIVITY_THRESHOLD", "0.3"))
RANKING_HALF_LIFE_HOURS = float(os.environ.get("RANKING_HALF_LIFE_HOURS", "12.0"))
if RANKING_HALF_LIFE_HOURS <= 0:
    raise ValueError(f"RANKING_HALF_LIFE_HOURS ({RANKING_HALF_LIFE_HOURS}) must be greater than 0")
# Deliberately left at 72h even though 24h retention effectively caps it
# tighter today -- see CLAUDE.md's Data retention section before changing.
RANKING_MMR_WINDOW_HOURS = float(os.environ.get("RANKING_MMR_WINDOW_HOURS", "72.0"))
RANKING_MMR_CANDIDATE_POOL_SIZE = int(os.environ.get("RANKING_MMR_CANDIDATE_POOL_SIZE", "2000"))
RANKING_MMR_LAMBDA = float(os.environ.get("RANKING_MMR_LAMBDA", "0.7"))
RANKING_SIMILARITY_TFIDF_WEIGHT = float(os.environ.get("RANKING_SIMILARITY_TFIDF_WEIGHT", "0.5"))
RANKING_SIMILARITY_ENTITY_WEIGHT = float(os.environ.get("RANKING_SIMILARITY_ENTITY_WEIGHT", "0.5"))
# Source-diversity signal, not a content-similarity one -- two posts from the
# same author count as "similar" for MMR's diversity penalty regardless of
# topic overlap, so one prolific source can't crowd out other quality
# sources just by posting more. 20x TFIDF_WEIGHT/ENTITY_WEIGHT's default,
# deliberately: a source with a genuinely deep reserve of individually
# high-scoring posts can keep refilling MMR's selection from that reserve
# once cheaper diverse alternatives run out, unless the same-author
# penalty is large enough to make even the deepest reserve unattractive --
# a real news story covered by many different authors doesn't have that
# dynamic, since its supply is naturally finite, which is why the
# content-similarity weights don't need the same scale.
# See the wiki's Ranking page.
RANKING_SIMILARITY_AUTHOR_WEIGHT = float(os.environ.get("RANKING_SIMILARITY_AUTHOR_WEIGHT", "10.0"))


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
    # Raw, not canonicalized -- _similarity_matrix runs both through
    # bot_filter.canonical_account_id itself, the same normalization
    # velocity/self-dup/template already rely on, so a real account
    # crossposted or federated across several polled Mastodon instances
    # doesn't fragment into several apparently-diverse "authors" here too.
    source: str
    author_id: str
    # context_dependency.py's per-platform devalue multiplier -- 1.0 for
    # posts that aren't context-dependent (or whose platform's policy is
    # exclude-only, so a devalued post never reaches ranking at all).
    # Content-derived, same category as topicality/sentiment, not an
    # engagement signal.
    context_penalty: float = 1.0
    # link_share.py's bare-link-share devalue multiplier -- 1.0 unless the
    # post's own text adds nothing beyond its link card's title. Same
    # content-derived, non-engagement category as context_penalty.
    link_share_penalty: float = 1.0


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
    (the ranking window is only applied later, in rank_posts), so this has
    to handle arbitrarily old posts. Anything decaying below Postgres's
    REAL (float4) underflow range snaps to exactly 0.0 instead of raising
    on write -- see the wiki's Ranking page."""
    age_hours = max(0.0, (now - created_at).total_seconds() / 3600.0)
    decay = 0.5 ** (age_hours / RANKING_HALF_LIFE_HOURS)
    return decay if decay >= MIN_DECAY else 0.0


def compute_base_score(post: RankablePost, now: datetime) -> float:
    """Content-derived only — positivity x topicality x recency x
    context_penalty x link_share_penalty. No engagement field exists on
    RankablePost for this to accidentally read."""
    return (
        positivity(post.sentiment_score)
        * post.topicality_score
        * recency_decay(post.created_at, now)
        * post.context_penalty
        * post.link_share_penalty
    )


def filter_eligible(posts: list[RankablePost]) -> list[RankablePost]:
    return [
        p
        for p in posts
        if not p.is_bot and p.is_dedup_canonical and p.sentiment_score >= RANKING_POSITIVITY_THRESHOLD
    ]


def _entity_similarity_matrix(entity_lists: list[list[str]]) -> np.ndarray:
    """Pairwise Jaccard similarity for n sets, vectorized as one sparse
    matrix multiply instead of a pure-Python O(n^2) double loop -- build an
    n x |vocab| binary "post mentions entity" matrix M; M @ M.T gives
    pairwise intersection counts in a single (C-level) sparse matmul, and
    union follows from each set's own size via broadcasting. See the
    wiki's Ranking page for why this matters at real production volume."""
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


def _author_similarity_matrix(canonical_author_ids: list[str]) -> np.ndarray:
    """1.0 for any two posts from the same canonical author, 0.0 otherwise --
    binary, not graded like TF-IDF/entity similarity, since account identity
    either matches or doesn't. Captures the diversity dimension neither of
    those two signals can: two posts from the same author can be about
    completely different topics and still both be competing for the same
    discovery opportunity every other source is competing for. See the
    wiki's Ranking page."""
    n = len(canonical_author_ids)
    if n == 0:
        return np.zeros((0, 0))
    _, codes = np.unique(canonical_author_ids, return_inverse=True)
    same_author = (codes[:, None] == codes[None, :]).astype(float)
    np.fill_diagonal(same_author, 0.0)  # self-similarity is never consulted, but keep it clean
    return same_author


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
    # Canonicalized here, not stored on RankablePost -- a cheap pure-string
    # operation, so recomputing it per ranking pass keeps one single code
    # path regardless of which construction site (run_cycle vs
    # refresh_rankings) built the post, rather than threading a precomputed
    # id through bot_filter.py's BotScore for one call site but not the other.
    author_sim = _author_similarity_matrix(
        [bot_filter.canonical_account_id(p.source, p.author_id) for p in posts]
    )

    return (
        RANKING_SIMILARITY_TFIDF_WEIGHT * tfidf_sim
        + RANKING_SIMILARITY_ENTITY_WEIGHT * entity_sim
        + RANKING_SIMILARITY_AUTHOR_WEIGHT * author_sim
    )


def rank_posts(posts: list[RankablePost], now: datetime | None = None) -> dict[UUID, RankResult]:
    """Filters to eligible posts within a recent window, computes a content-
    derived base_score (positivity x topicality x recency), then greedily
    selects posts by Maximal Marginal Relevance so near-duplicate topics
    don't dominate the feed. Selection order becomes rank_score — provably
    non-increasing across rounds (each round's winner is bounded by the
    previous round's max), so `ORDER BY rank_score DESC` in the API
    reproduces this exact order. See the wiki's Ranking page."""
    if now is None:
        now = datetime.now(timezone.utc)

    eligible = filter_eligible(posts)
    cutoff = now - timedelta(hours=RANKING_MMR_WINDOW_HOURS)
    windowed = [p for p in eligible if p.created_at >= cutoff]

    results: dict[UUID, RankResult] = {}
    if not windowed:
        return results

    base_scores = {p.id: compute_base_score(p, now) for p in windowed}

    # A size-based cap on top of the time-based window above -- the
    # eligible pool can hold far more than a feed ever surfaces, and the
    # O(n^2) similarity pass below is memory-bound, not just compute-bound.
    # Self-correcting: the pool is reselected fresh every cycle, so a post
    # that misses the cut can still enter later once higher-scoring posts
    # decay past it. See the wiki's Ranking page.
    if len(windowed) > RANKING_MMR_CANDIDATE_POOL_SIZE:
        windowed = sorted(windowed, key=lambda p: base_scores[p.id], reverse=True)[
            :RANKING_MMR_CANDIDATE_POOL_SIZE
        ]

    sim_matrix = _similarity_matrix(windowed)

    # Greedy MMR: each round needs the *current* best remaining candidate
    # given everything already selected, which is inherently sequential --
    # but tracked with a running per-post "max similarity to anything
    # selected so far" vector instead of recomputing it from scratch for
    # every remaining post on every round. See the wiki's Ranking page.
    n = len(windowed)
    base_scores_arr = np.array([base_scores[p.id] for p in windowed])
    max_sim_to_selected = np.zeros(n)
    remaining_mask = np.ones(n, dtype=bool)

    for rank_position in range(n):
        mmr_values = RANKING_MMR_LAMBDA * base_scores_arr - (1 - RANKING_MMR_LAMBDA) * max_sim_to_selected
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
