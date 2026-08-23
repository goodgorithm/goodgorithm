import pipeline
from infra.db import UncheckedBlueskyPost, UnresolvedAuthorPost


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


def test_resolve_authors_noop_when_nothing_unresolved(monkeypatch):
    monkeypatch.setattr(pipeline.db, "fetch_bluesky_posts_needing_author_resolution", lambda batch_size: [])
    monkeypatch.setattr(pipeline.db, "mark_authors_resolved", lambda results: None)

    assert pipeline.resolve_authors() == 0


def test_resolve_authors_marks_resolved_and_skips_failed_batch(monkeypatch):
    posts = [
        UnresolvedAuthorPost(raw_post_id="found-id", source_id="did:plc:a/1", author_id="did:plc:a"),
        UnresolvedAuthorPost(raw_post_id="no-author-id", source_id="did:plc:b/2", author_id="did:plc:b"),
        UnresolvedAuthorPost(raw_post_id="unresolved-id", source_id="did:plc:c/3", author_id="did:plc:c"),
    ]
    monkeypatch.setattr(pipeline.db, "fetch_bluesky_posts_needing_author_resolution", lambda batch_size: posts)
    monkeypatch.setattr(
        pipeline.author_resolver,
        "resolve_authors",
        lambda posts: {
            "found-id": {"displayName": "Jane Doe", "avatarUrl": None},
            "no-author-id": None,  # checked, but nothing to report
            # "unresolved-id" absent entirely -- its batch "failed"
        },
    )

    marked = []
    monkeypatch.setattr(pipeline.db, "mark_authors_resolved", lambda results: marked.extend(results))

    assert pipeline.resolve_authors() == 1  # only "found-id" actually has author data
    assert marked == [
        ("found-id", {"displayName": "Jane Doe", "avatarUrl": None}),
        ("no-author-id", None),
    ]
