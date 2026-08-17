import pipeline


def test_refresh_rankings_runs_without_error(monkeypatch):
    # Regression test: pipeline.py referenced ranking.MMR_WINDOW_HOURS after
    # ranking.py's tunables were renamed to a RANKING_-prefixed scheme,
    # crash-looping processing in both staging and production every cycle
    # (refresh_rankings raised AttributeError, and nothing in the test
    # suite called this function to catch it).
    monkeypatch.setattr(pipeline.db, "fetch_rankable_posts", lambda since: [])
    monkeypatch.setattr(pipeline.db, "update_rank_scores", lambda updates: None)

    assert pipeline.refresh_rankings() == 0
