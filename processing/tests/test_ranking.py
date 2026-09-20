import random
import string
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pipeline_stages import ranking

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_post(
    quality_score=0.5,
    entities=None,
    age_hours=0.0,
    is_bot=False,
    is_dedup_canonical=True,
    text="a distinct post about nothing in particular",
    source=None,
    author_id=None,
):
    # A fresh unique author per call by default, so unmodified tests don't
    # accidentally collide into "same author" with each other now that
    # author identity feeds MMR's similarity signal.
    return ranking.RankablePost(
        id=uuid4(),
        text=text,
        created_at=NOW - timedelta(hours=age_hours),
        quality_score=quality_score,
        entities=entities or [],
        is_bot=is_bot,
        is_dedup_canonical=is_dedup_canonical,
        source=source or "bluesky",
        author_id=author_id or str(uuid4()),
    )


def test_recency_decay_half_life():
    fresh = make_post(age_hours=0.0)
    at_half_life = make_post(age_hours=ranking.RANKING_HALF_LIFE_HOURS)
    older = make_post(age_hours=ranking.RANKING_HALF_LIFE_HOURS * 2)

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


def test_compute_base_score_multiplies_quality_by_recency():
    post = make_post(quality_score=0.8, age_hours=0.0)
    assert abs(ranking.compute_base_score(post, NOW) - 0.8) < 1e-9  # 0.8 * decay(1.0)


def test_compute_base_score_scales_with_recency_decay():
    fresh = make_post(quality_score=0.8, age_hours=0.0)
    half_life = make_post(quality_score=0.8, age_hours=ranking.RANKING_HALF_LIFE_HOURS)
    assert abs(ranking.compute_base_score(half_life, NOW) - ranking.compute_base_score(fresh, NOW) * 0.5) < 1e-9


def test_compute_base_score_degrades_to_zero_when_quality_score_missing():
    # quality_score is only ever None during a quality-model outage
    # (quality_exclude.py fails open rather than blocking the whole feed) --
    # compute_base_score must degrade, not crash on None * float.
    post = make_post(quality_score=None)
    assert ranking.compute_base_score(post, NOW) == 0.0


def test_filter_eligible_excludes_bots_and_duplicates():
    good = make_post()
    bot = make_post(is_bot=True)
    duplicate = make_post(is_dedup_canonical=False)

    eligible = ranking.filter_eligible([good, bot, duplicate])

    assert eligible == [good]


def test_rank_posts_excludes_posts_outside_the_window():
    recent = make_post(age_hours=1.0, text="a fresh post about local news")
    stale = make_post(age_hours=ranking.RANKING_MMR_WINDOW_HOURS + 1, text="an old post about local news")

    results = ranking.rank_posts([recent, stale], now=NOW)

    assert recent.id in results
    assert stale.id not in results


def test_rank_posts_empty_input_returns_empty():
    assert ranking.rank_posts([], now=NOW) == {}


def test_rank_posts_orders_by_base_score_when_no_topical_overlap():
    # three unrelated posts, no shared entities/text — MMR's diversity term
    # is ~0 for all pairs, so order should just follow base_score.
    high = make_post(quality_score=0.9, text="a big story about volcanoes erupting")
    mid = make_post(quality_score=0.5, text="a smaller story about local gardening")
    low = make_post(quality_score=0.3, text="a quiet note about weekend weather")

    results = ranking.rank_posts([high, mid, low], now=NOW)

    assert results[high.id].rank_position == 0
    assert results[mid.id].rank_position == 1
    assert results[low.id].rank_position == 2


def test_rank_score_is_non_increasing_across_selection_order():
    posts = [
        make_post(quality_score=s, text=f"story number {i} about topic {i}")
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
        quality_score=1.0, entities=earthquake_entities,
        text="Earthquake strikes California coast this morning",
    )
    e2 = make_post(
        quality_score=0.95, entities=earthquake_entities,
        text="California earthquake confirmed by seismologists",
    )
    e3 = make_post(
        quality_score=0.9, entities=earthquake_entities,
        text="More details emerge on the California earthquake",
    )
    diverse = make_post(
        quality_score=0.7, entities=["sourdough"],
        text="Local bakery wins national award for best sourdough",
    )

    results = ranking.rank_posts([e1, e2, e3, diverse], now=NOW)
    ordered = sorted(results.items(), key=lambda kv: kv[1].rank_position)
    order = [post_id for post_id, _ in ordered]

    assert order[0] == e1.id  # highest raw base_score still goes first
    assert order.index(diverse.id) < order.index(e2.id)
    assert order.index(diverse.id) < order.index(e3.id)


def test_mmr_spreads_out_same_author_regardless_of_topic():
    # Mirrors test_mmr_spreads_out_near_duplicate_topics, but the crowding
    # signal here is authorship, not topic -- three posts from one prolific
    # author (high base_score, but each about a *different*, non-overlapping
    # topic -- e.g. christiansongz's differently-titled songs) plus one
    # lower-scoring post from a different author. MMR should still pull the
    # different author ahead of at least one same-author post, even though
    # nothing about content similarity would do that on its own.
    author = "prolific@example.social"
    a1 = make_post(
        quality_score=1.0, source="mastodon", author_id=author,
        entities=["jazz album"], text="reviewing a new jazz album from a local artist",
    )
    a2 = make_post(
        quality_score=0.95, source="mastodon", author_id=author,
        entities=["short film"], text="a short film premiered at the neighborhood theater",
    )
    a3 = make_post(
        quality_score=0.9, source="mastodon", author_id=author,
        entities=["mural"], text="a mural was painted downtown this weekend",
    )
    diverse = make_post(
        quality_score=0.7, source="mastodon", author_id="other@example.social",
        entities=["bridge"], text="a bridge reopened after repairs",
    )

    results = ranking.rank_posts([a1, a2, a3, diverse], now=NOW)
    ordered = sorted(results.items(), key=lambda kv: kv[1].rank_position)
    order = [post_id for post_id, _ in ordered]

    assert order[0] == a1.id  # highest raw base_score still goes first
    assert order.index(diverse.id) < order.index(a2.id)
    assert order.index(diverse.id) < order.index(a3.id)


def test_author_similarity_uses_canonical_account_id():
    # Same real Mastodon account, seen via two different polled instances --
    # canonical_account_id normalizes both to the same identity regardless
    # of which instance polled it. Without that normalization, these would
    # incorrectly look like two different authors and get no diversity
    # credit against each other, reopening the exact fragmentation bug
    # bot_filter.py's canonical_account_id already fixed once.
    same_account_a = make_post(
        source="mastodon", author_id="universeodon.com/same@remote.example",
        entities=["jazz album"], text="reviewing a new jazz album from a local artist",
    )
    same_account_b = make_post(
        source="mastodon", author_id="mstdn.social/same@remote.example",
        entities=["short film"], text="a short film premiered at the neighborhood theater",
    )
    different_account = make_post(
        source="mastodon", author_id="universeodon.com/other@remote.example",
        entities=["mural"], text="a mural was painted downtown this weekend",
    )

    sim = ranking._similarity_matrix([same_account_a, same_account_b, different_account])

    assert abs(sim[0][1] - ranking.RANKING_SIMILARITY_AUTHOR_WEIGHT) < 1e-9
    assert sim[0][2] == 0.0
    assert sim[1][2] == 0.0


def test_author_similarity_is_zero_for_different_authors():
    # Two genuinely different Bluesky accounts (bare DIDs, passed through
    # canonical_account_id unchanged) with zero content overlap -- confirms
    # the new signal doesn't spuriously penalize genuinely diverse authors.
    bluesky_a = make_post(
        source="bluesky", author_id="did:plc:aaaa",
        entities=["garden"], text="a garden bloomed early this spring",
    )
    bluesky_b = make_post(
        source="bluesky", author_id="did:plc:bbbb",
        entities=["bridge"], text="a bridge reopened after repairs",
    )

    sim = ranking._similarity_matrix([bluesky_a, bluesky_b])

    assert sim[0][1] == 0.0


def test_rank_posts_scales_to_production_volume():
    # Regression test: the entity-similarity pass and the MMR selection
    # loop are both vectorized, not pure-Python O(n^2) -- see the wiki's
    # Ranking page. A generous time bound (not a tight one -- CI machines
    # vary) exists specifically to catch a regression back to O(n^2)
    # Python loops, which would blow well past it at this n.
    rng = random.Random(1234)

    def make_random_post(i):
        entities = ["".join(rng.choices(string.ascii_lowercase, k=6)) for _ in range(rng.randint(0, 5))]
        text = " ".join("".join(rng.choices(string.ascii_lowercase, k=6)) for _ in range(rng.randint(10, 40)))
        return ranking.RankablePost(
            id=uuid4(),
            text=text,
            created_at=NOW - timedelta(minutes=i),
            quality_score=rng.uniform(0.39, 1.0),
            entities=entities,
            is_bot=False,
            is_dedup_canonical=True,
            source="bluesky",
            author_id=str(uuid4()),
        )

    posts = [make_random_post(i) for i in range(2000)]

    start = time.monotonic()
    results = ranking.rank_posts(posts, now=NOW)
    elapsed = time.monotonic() - start

    assert len(results) == len(posts)
    assert elapsed < 15.0, f"rank_posts took {elapsed:.1f}s for 2000 posts - likely an O(n^2) Python-loop regression"


def test_rank_posts_caps_candidate_pool_by_base_score():
    # Regression test: _similarity_matrix's dense n x n float64 arrays
    # scale badly with the eligible pool's size, not just its compute time
    # -- see the wiki's Ranking page for why rank_posts caps the candidate
    # pool to RANKING_MMR_CANDIDATE_POOL_SIZE before building any O(n^2)
    # structure.
    n = ranking.RANKING_MMR_CANDIDATE_POOL_SIZE + 500
    posts = [
        ranking.RankablePost(
            id=uuid4(),
            text=f"distinct post number {i} about nothing in particular",
            created_at=NOW,
            quality_score=0.39 + (i / n) * 0.61,  # strictly increasing base_score
            entities=[],
            is_bot=False,
            is_dedup_canonical=True,
            source="bluesky",
            author_id=str(uuid4()),
        )
        for i in range(n)
    ]

    results = ranking.rank_posts(posts, now=NOW)

    assert len(results) == ranking.RANKING_MMR_CANDIDATE_POOL_SIZE
    # the lowest-base_score posts (smallest i) must be the ones dropped
    kept_ids = set(results)
    dropped = [p for p in posts if p.id not in kept_ids]
    kept = [p for p in posts if p.id in kept_ids]
    assert max(p.quality_score for p in dropped) <= min(p.quality_score for p in kept)
