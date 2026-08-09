import random
import string
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import ranking

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_post(
    sentiment_score=0.5,
    topicality_score=1.0,
    entities=None,
    age_hours=0.0,
    is_bot=False,
    is_dedup_canonical=True,
    text="a distinct post about nothing in particular",
):
    return ranking.RankablePost(
        id=uuid4(),
        text=text,
        created_at=NOW - timedelta(hours=age_hours),
        sentiment_score=sentiment_score,
        topicality_score=topicality_score,
        entities=entities or [],
        is_bot=is_bot,
        is_dedup_canonical=is_dedup_canonical,
    )


def test_positivity_clamps_negative_to_zero():
    assert ranking.positivity(-0.5) == 0.0
    assert ranking.positivity(0.0) == 0.0
    assert ranking.positivity(0.8) == 0.8


def test_recency_decay_half_life():
    fresh = make_post(age_hours=0.0)
    at_half_life = make_post(age_hours=ranking.HALF_LIFE_HOURS)
    older = make_post(age_hours=ranking.HALF_LIFE_HOURS * 2)

    assert ranking.recency_decay(fresh.created_at, NOW) == 1.0
    assert abs(ranking.recency_decay(at_half_life.created_at, NOW) - 0.5) < 1e-9
    assert ranking.recency_decay(older.created_at, NOW) < ranking.recency_decay(at_half_life.created_at, NOW)


def test_recency_decay_snaps_to_zero_for_very_old_posts():
    # run_cycle() computes base_score for every fetched post unconditionally
    # (no age bound -- that only applies later, in rank_posts), so real
    # backlog/boosted content genuinely months old must not produce a
    # nonzero-but-unrepresentable-in-REAL value (Postgres NumericValueOutOfRange).
    very_old = make_post(age_hours=535 * 24)  # ~535 days, a real value seen in production
    assert ranking.recency_decay(very_old.created_at, NOW) == 0.0


def test_compute_base_score_multiplies_components():
    post = make_post(sentiment_score=0.5, topicality_score=2.0, age_hours=0.0)
    assert abs(ranking.compute_base_score(post, NOW) - 1.0) < 1e-9  # positivity(0.5) * 2.0 * decay(1.0)


def test_filter_eligible_excludes_bots_duplicates_and_low_sentiment():
    good = make_post(sentiment_score=0.5)
    bot = make_post(sentiment_score=0.5, is_bot=True)
    duplicate = make_post(sentiment_score=0.5, is_dedup_canonical=False)
    too_neutral = make_post(sentiment_score=ranking.POSITIVITY_THRESHOLD - 0.01)

    eligible = ranking.filter_eligible([good, bot, duplicate, too_neutral])

    assert eligible == [good]


def test_rank_posts_excludes_posts_outside_the_window():
    recent = make_post(age_hours=1.0, text="a fresh post about local news")
    stale = make_post(age_hours=ranking.MMR_WINDOW_HOURS + 1, text="an old post about local news")

    results = ranking.rank_posts([recent, stale], now=NOW)

    assert recent.id in results
    assert stale.id not in results


def test_rank_posts_empty_input_returns_empty():
    assert ranking.rank_posts([], now=NOW) == {}


def test_rank_posts_orders_by_base_score_when_no_topical_overlap():
    # three unrelated posts, no shared entities/text — MMR's diversity term
    # is ~0 for all pairs, so order should just follow base_score.
    high = make_post(sentiment_score=0.9, topicality_score=1.0, text="a big story about volcanoes erupting")
    mid = make_post(sentiment_score=0.5, topicality_score=1.0, text="a smaller story about local gardening")
    low = make_post(sentiment_score=0.3, topicality_score=1.0, text="a quiet note about weekend weather")

    results = ranking.rank_posts([high, mid, low], now=NOW)

    assert results[high.id].rank_position == 0
    assert results[mid.id].rank_position == 1
    assert results[low.id].rank_position == 2


def test_rank_score_is_non_increasing_across_selection_order():
    posts = [
        make_post(sentiment_score=s, topicality_score=1.0, text=f"story number {i} about topic {i}")
        for i, s in enumerate([0.9, 0.4, 0.7, 0.5, 0.3])
    ]
    results = ranking.rank_posts(posts, now=NOW)
    ordered = sorted(results.values(), key=lambda r: r.rank_position)
    scores = [r.rank_score for r in ordered]
    assert scores == sorted(scores, reverse=True)


def test_mmr_spreads_out_near_duplicate_topics():
    # three near-duplicate earthquake posts (high base_score, shared
    # entities) plus one distinct, lower-scoring post — MMR should pull
    # the distinct post ahead of at least one higher-scoring duplicate.
    earthquake_entities = ["california", "earthquake"]
    e1 = make_post(
        sentiment_score=0.5, topicality_score=1.0, entities=earthquake_entities,
        text="Earthquake strikes California coast this morning",
    )
    e2 = make_post(
        sentiment_score=0.5, topicality_score=0.95, entities=earthquake_entities,
        text="California earthquake confirmed by seismologists",
    )
    e3 = make_post(
        sentiment_score=0.5, topicality_score=0.9, entities=earthquake_entities,
        text="More details emerge on the California earthquake",
    )
    diverse = make_post(
        sentiment_score=0.5, topicality_score=0.7, entities=["sourdough"],
        text="Local bakery wins national award for best sourdough",
    )

    results = ranking.rank_posts([e1, e2, e3, diverse], now=NOW)
    ordered = sorted(results.items(), key=lambda kv: kv[1].rank_position)
    order = [post_id for post_id, _ in ordered]

    assert order[0] == e1.id  # highest raw base_score still goes first
    assert order.index(diverse.id) < order.index(e2.id)
    assert order.index(diverse.id) < order.index(e3.id)


def test_rank_posts_scales_to_production_volume():
    # Regression test for a real 2026-08-09 production incident: the MMR
    # window can genuinely hold thousands of eligible posts (5,238 seen in
    # prod), and both the entity-similarity pass and the MMR selection loop
    # used to be pure-Python O(n^2) - tens of millions of interpreted
    # operations, slow and memory-hungry enough that the process was
    # silently OOM-killed every cycle with no traceback. Both are now
    # vectorized (see _entity_similarity_matrix and rank_posts). A generous
    # time bound here (not a tight one - CI machines vary) exists
    # specifically to catch a regression back to the O(n^2) Python loops,
    # which would blow well past it at this n.
    rng = random.Random(1234)

    def make_random_post(i):
        entities = ["".join(rng.choices(string.ascii_lowercase, k=6)) for _ in range(rng.randint(0, 5))]
        text = " ".join("".join(rng.choices(string.ascii_lowercase, k=6)) for _ in range(rng.randint(10, 40)))
        return ranking.RankablePost(
            id=uuid4(),
            text=text,
            created_at=NOW - timedelta(minutes=i),
            sentiment_score=rng.uniform(0.3, 1.0),
            topicality_score=rng.uniform(0.5, 2.0),
            entities=entities,
            is_bot=False,
            is_dedup_canonical=True,
        )

    posts = [make_random_post(i) for i in range(2000)]

    start = time.monotonic()
    results = ranking.rank_posts(posts, now=NOW)
    elapsed = time.monotonic() - start

    assert len(results) == len(posts)
    assert elapsed < 15.0, f"rank_posts took {elapsed:.1f}s for 2000 posts - likely an O(n^2) Python-loop regression"


def test_rank_posts_caps_candidate_pool_by_base_score():
    # Regression test for a real 2026-08-09 production incident: the MMR
    # window held 29,770 eligible posts (still growing) by the time this
    # was diagnosed. _similarity_matrix's vectorized-but-still-dense n x n
    # float64 arrays are ~7GB at that n - the earlier vectorization fix
    # (ea4fcb6) made the O(n^2) pass fast, not small, and the process was
    # OOM-killed on a 1GB container regardless. rank_posts now caps the
    # pool to the top MMR_CANDIDATE_POOL_SIZE posts by base_score before
    # building any O(n^2) structure, bounding memory no matter how large
    # the eligible window grows.
    n = ranking.MMR_CANDIDATE_POOL_SIZE + 500
    posts = [
        ranking.RankablePost(
            id=uuid4(),
            text=f"distinct post number {i} about nothing in particular",
            created_at=NOW,
            sentiment_score=0.3 + (i / n) * 0.7,  # strictly increasing base_score
            topicality_score=1.0,
            entities=[],
            is_bot=False,
            is_dedup_canonical=True,
        )
        for i in range(n)
    ]

    results = ranking.rank_posts(posts, now=NOW)

    assert len(results) == ranking.MMR_CANDIDATE_POOL_SIZE
    # the lowest-base_score posts (smallest i) must be the ones dropped
    kept_ids = set(results)
    dropped = [p for p in posts if p.id not in kept_ids]
    kept = [p for p in posts if p.id in kept_ids]
    assert max(p.sentiment_score for p in dropped) <= min(p.sentiment_score for p in kept)
