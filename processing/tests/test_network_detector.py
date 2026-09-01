from datetime import datetime, timezone

from infra import db, network_detector


def make_candidate(home_domain="example.com", account_count=6) -> db.ClusterCandidate:
    return db.ClusterCandidate(
        home_domain=home_domain,
        author_ids=[f"mas.to/user{i}@{home_domain}" for i in range(account_count)],
        account_count=account_count,
        post_count=100,
        earliest_account_created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        latest_account_created_at=datetime(2026, 2, 10, tzinfo=timezone.utc),
    )


def make_bsky_cluster(n_dids=8) -> db.BlueskyFunnelCluster:
    return db.BlueskyFunnelCluster(
        dids=[f"did:plc:funnel{i}" for i in range(n_dids)],
        post_count=n_dids * 2,
        earliest_created_at=datetime(2026, 9, 1, 0, tzinfo=timezone.utc),
        latest_created_at=datetime(2026, 9, 1, 12, tzinfo=timezone.utc),
        sample_captions=["not posting it twice, check my bio instead 🤫"],
    )


def test_detect_clusters_passes_the_configured_thresholds(monkeypatch):
    captured = {}

    def fake_fetch(min_accounts, max_creation_span_days, min_post_count):
        captured["min_accounts"] = min_accounts
        captured["max_creation_span_days"] = max_creation_span_days
        captured["min_post_count"] = min_post_count
        return []

    monkeypatch.setattr(db, "fetch_cluster_candidates", fake_fetch)

    network_detector.detect_clusters()

    assert captured == {
        "min_accounts": network_detector.NETWORK_DETECTOR_MIN_CLUSTER_ACCOUNTS,
        "max_creation_span_days": network_detector.NETWORK_DETECTOR_MAX_ACCOUNT_CREATION_SPAN_DAYS,
        "min_post_count": network_detector.NETWORK_DETECTOR_MIN_CLUSTER_POST_COUNT,
    }


def test_record_clusters_upserts_and_returns_the_count(monkeypatch):
    upserted = []
    monkeypatch.setattr(db, "upsert_flagged_clusters", lambda candidates: upserted.extend(candidates))

    candidates = [make_candidate("a.example"), make_candidate("b.example")]
    result = network_detector.record_clusters(candidates)

    assert upserted == candidates
    assert result == 2


def test_record_clusters_with_no_candidates_still_calls_upsert(monkeypatch):
    calls = []
    monkeypatch.setattr(db, "upsert_flagged_clusters", lambda candidates: calls.append(candidates))

    result = network_detector.record_clusters([])

    assert calls == [[]]
    assert result == 0


def test_detect_bluesky_funnel_cluster_passes_the_configured_thresholds(monkeypatch):
    captured = {}

    def fake(window_hours, min_adult_hashtags, min_dids, cta_pattern, adult_vocab):
        captured.update(
            window_hours=window_hours,
            min_adult_hashtags=min_adult_hashtags,
            min_dids=min_dids,
            cta_pattern=cta_pattern,
            adult_vocab=adult_vocab,
        )
        return None

    monkeypatch.setattr(db, "fetch_bluesky_funnel_cluster", fake)

    assert network_detector.detect_bluesky_funnel_cluster() == []
    assert captured["window_hours"] == network_detector.NETWORK_DETECTOR_BLUESKY_FUNNEL_WINDOW_HOURS
    assert captured["min_adult_hashtags"] == network_detector.NETWORK_DETECTOR_BLUESKY_FUNNEL_MIN_ADULT_HASHTAGS
    assert captured["min_dids"] == network_detector.NETWORK_DETECTOR_BLUESKY_FUNNEL_MIN_DIDS
    assert "in my bio" in captured["cta_pattern"]
    assert "egirl" in captured["adult_vocab"]


def test_detect_bluesky_funnel_cluster_maps_to_a_synthetic_key_candidate(monkeypatch):
    monkeypatch.setattr(db, "fetch_bluesky_funnel_cluster", lambda **kw: make_bsky_cluster(8))

    out = network_detector.detect_bluesky_funnel_cluster()

    assert len(out) == 1
    c = out[0]
    assert c.home_domain == "bluesky:funnel-network"
    assert c.account_count == 8
    assert len(c.author_ids) == 8
    assert c.post_count == 16
    assert c.earliest_account_created_at == datetime(2026, 9, 1, 0, tzinfo=timezone.utc)
    assert c.latest_account_created_at == datetime(2026, 9, 1, 12, tzinfo=timezone.utc)


def test_detect_bluesky_funnel_cluster_returns_empty_when_no_cluster(monkeypatch):
    monkeypatch.setattr(db, "fetch_bluesky_funnel_cluster", lambda **kw: None)
    assert network_detector.detect_bluesky_funnel_cluster() == []


def test_record_clusters_upserts_mastodon_and_bluesky_candidates_together(monkeypatch):
    upserted = []
    monkeypatch.setattr(db, "upsert_flagged_clusters", lambda cands: upserted.extend(cands))
    monkeypatch.setattr(db, "fetch_bluesky_funnel_cluster", lambda **kw: make_bsky_cluster(6))

    candidates = [make_candidate("a.example")] + network_detector.detect_bluesky_funnel_cluster()
    result = network_detector.record_clusters(candidates)

    assert result == 2
    assert {c.home_domain for c in upserted} == {"a.example", "bluesky:funnel-network"}
