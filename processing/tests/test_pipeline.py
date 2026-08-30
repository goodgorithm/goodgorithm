import pipeline
from infra.db import RawPost, UncheckedBlueskyPost, UnresolvedAuthorPost
from pipeline_stages.context_dependency import ContextClassification


def test_refresh_rankings_runs_without_error(monkeypatch):
    # Regression test: pipeline.py referenced ranking.MMR_WINDOW_HOURS after
    # ranking.py's tunables were renamed to a RANKING_-prefixed scheme,
    # crash-looping processing in both staging and production every cycle
    # (refresh_rankings raised AttributeError, and nothing in the test
    # suite called this function to catch it).
    monkeypatch.setattr(pipeline.db, "fetch_rankable_posts", lambda since, min_sentiment, pool_size: [])
    monkeypatch.setattr(pipeline.db, "update_rank_scores", lambda updates: None)

    assert pipeline.refresh_rankings() == 0


def test_refresh_rankings_pushes_eligibility_and_pool_size_into_the_query(monkeypatch):
    captured = {}

    def fake_fetch(since, min_sentiment, pool_size):
        captured["min_sentiment"] = min_sentiment
        captured["pool_size"] = pool_size
        return []

    monkeypatch.setattr(pipeline.db, "fetch_rankable_posts", fake_fetch)
    monkeypatch.setattr(pipeline.db, "update_rank_scores", lambda updates: None)

    pipeline.refresh_rankings()

    assert captured["min_sentiment"] == pipeline.ranking.RANKING_POSITIVITY_THRESHOLD
    assert captured["pool_size"] == pipeline.ranking.RANKING_MMR_CANDIDATE_POOL_SIZE


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


def _raw_post(id_, source, lang, text):
    return RawPost(
        id=id_,
        source=source,
        source_id=f"{source}:{id_}",
        author_id=f"author-{id_}",
        text=text,
        lang=lang,
        created_at=None,
        raw_json={},
    )


def test_run_cycle_language_gate_covers_untrusted_bluesky_tags(monkeypatch):
    # issue #107: the fastText re-check runs on an untagged post, on any
    # Mastodon post, and now also on a Bluesky post whose `langs` tag can't
    # be trusted (non-Latin body under `en`, or a non-English primary
    # tag) -- but NOT on a plain Latin-script `en` Bluesky post.
    posts = [
        _raw_post("bsky-untagged", "bluesky", None, "algo de texto aqui"),
        _raw_post("masto-en", "mastodon", "en", "irgendein text hier"),
        _raw_post("bsky-en-thai", "bluesky", "en", "ขอเลื่อนไลฟ์เปิดกล้องมาเร็ว"),
        _raw_post("bsky-es", "bluesky", "es", "Creo que es la mejor de la tarde."),
        _raw_post("bsky-en-latin", "bluesky", "en", "im so excited hehe"),
    ]
    monkeypatch.setattr(pipeline.db, "fetch_unprocessed_posts", lambda batch_size: posts)
    monkeypatch.setattr(pipeline.db, "fetch_moderation_lists", lambda: (set(), [], [], frozenset()))
    monkeypatch.setattr(pipeline.content_filter, "is_content_excluded", lambda *a, **k: False)

    checked = []
    monkeypatch.setattr(
        pipeline.language_filter,
        "is_non_english",
        lambda text: checked.append(text) or True,  # every text that reaches fastText is "non-English"
    )
    # Anything surviving the language gate is context-excluded, so kept_posts
    # stays empty and run_cycle returns before any scoring machinery.
    monkeypatch.setattr(
        pipeline.context_dependency, "classify", lambda *a, **k: ContextClassification(action="exclude")
    )
    deleted = []
    monkeypatch.setattr(pipeline.db, "delete_raw_post", lambda post_id: deleted.append(post_id))

    assert pipeline.run_cycle(batch_size=10) == len(posts)
    # fastText was consulted for exactly the untrusted-tag posts...
    assert set(checked) == {
        "algo de texto aqui",
        "irgendein text hier",
        "ขอเลื่อนไลฟ์เปิดกล้องมาเร็ว",
        "Creo que es la mejor de la tarde.",
    }
    # ...and never for the plain Latin `en` Bluesky post.
    assert "im so excited hehe" not in checked
