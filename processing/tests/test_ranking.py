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
