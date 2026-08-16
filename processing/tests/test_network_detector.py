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
