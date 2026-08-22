import pipeline
from infra.db import UncheckedBlueskyPost


def test_refresh_rankings_runs_without_error(monkeypatch):
    # Regression test: pipeline.py referenced ranking.MMR_WINDOW_HOURS after
    # ranking.py's tunables were renamed to a RANKING_-prefixed scheme,
    # crash-looping processing in both staging and production every cycle
    # (refresh_rankings raised AttributeError, and nothing in the test
    # suite called this function to catch it).
    monkeypatch.setattr(pipeline.db, "fetch_rankable_posts", lambda since: [])
    monkeypatch.setattr(pipeline.db, "update_rank_scores", lambda updates: None)

    assert pipeline.refresh_rankings() == 0


def test_recheck_moderation_noop_when_nothing_unchecked(monkeypatch):
    monkeypatch.setattr(pipeline.db, "fetch_unchecked_bluesky_posts", lambda batch_size: [])
    monkeypatch.setattr(pipeline.db, "mark_moderation_checked", lambda ids: None)

    assert pipeline.recheck_moderation() == 0


def test_recheck_moderation_purges_excluded_and_marks_clean_checked(monkeypatch):
    posts = [
        UncheckedBlueskyPost(raw_post_id="excluded-id", source_id="did:plc:a/1", author_id="did:plc:a"),
        UncheckedBlueskyPost(raw_post_id="clean-id", source_id="did:plc:b/2", author_id="did:plc:b"),
        UncheckedBlueskyPost(raw_post_id="unresolved-id", source_id="did:plc:c/3", author_id="did:plc:c"),
    ]
    monkeypatch.setattr(pipeline.db, "fetch_unchecked_bluesky_posts", lambda batch_size: posts)
    monkeypatch.setattr(
        pipeline.moderation_recheck,
        "check_posts",
        lambda posts: {"excluded-id": "excluded", "clean-id": "clean"},  # unresolved-id's batch "failed"
    )

    deleted = []
    monkeypatch.setattr(pipeline.db, "delete_raw_post", lambda post_id: deleted.append(post_id))
    checked = []
    monkeypatch.setattr(pipeline.db, "mark_moderation_checked", lambda ids: checked.extend(ids))

    assert pipeline.recheck_moderation() == 1
    assert deleted == ["excluded-id"]
    assert checked == ["clean-id"]
