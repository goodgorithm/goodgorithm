from datetime import datetime, timezone

import pytest

import pipeline
from infra.db import ContextPendingPost


def _reply_post(
    raw_post_id="reply-id",
    parent_uri="at://did:plc:parent/app.bsky.feed.post/p1",
    text="Yumm!",
    author_id="did:plc:author123",
    created_at=None,
):
    return ContextPendingPost(
        raw_post_id=raw_post_id,
        source="bluesky",
        author_id=author_id,
        text=text,
        raw_json={"commit": {"record": {"reply": {"parent": {"uri": parent_uri}}}}},
        context_kind="reply",
        # Effectively "now" -- age ~0 makes recency_decay ~1.0, so a
        # resolution's base_score assertion can compare directly against
        # its quality_score without needing to reproduce the decay math.
        created_at=created_at if created_at is not None else datetime.now(timezone.utc),
    )


def _mastodon_reply_post(
    raw_post_id="masto-reply-id",
    in_reply_to_id="42",
    text="Yumm!",
    author_id="mastodon.example/someone",
    created_at=None,
):
    return ContextPendingPost(
        raw_post_id=raw_post_id,
        source="mastodon",
        author_id=author_id,
        text=text,
        raw_json={"id": "99", "in_reply_to_id": in_reply_to_id, "content": "reply text"},
        context_kind="reply",
        created_at=created_at if created_at is not None else datetime.now(timezone.utc),
    )


def _stub_moderation(monkeypatch):
    monkeypatch.setattr(
        pipeline.db,
        "fetch_moderation_lists",
        lambda: pipeline.db.ModerationLists(frozenset(), frozenset(), frozenset(), {}),
    )


def _stub_permissive_filters(monkeypatch):
    """content/language/political/quality checks all pass -- individual
    tests override the one check they're exercising."""
    monkeypatch.setattr(pipeline.language_filter, "is_non_english", lambda text: False)
    monkeypatch.setattr(pipeline.political_exclude, "is_political_excluded", lambda c, s: False)
    monkeypatch.setattr(pipeline.quality_exclude, "is_quality_excluded", lambda score: False)
    monkeypatch.setattr(pipeline.db, "recent_bot_verdict", lambda source, author_id: None)


def test_resolve_context_noop_when_nothing_pending(monkeypatch):
    monkeypatch.setattr(pipeline.db, "fetch_context_pending", lambda batch_size: [])
    assert pipeline.resolve_context() == 0


def test_resolve_context_resolves_and_takes_min_of_own_and_target_quality(monkeypatch):
    post = _reply_post()
    monkeypatch.setattr(pipeline.db, "fetch_context_pending", lambda batch_size: [post])
    _stub_moderation(monkeypatch)
    _stub_permissive_filters(monkeypatch)

    monkeypatch.setattr(
        pipeline.quote_resolver,
        "resolve_context",
        lambda uris, terms, domains: (
            {post.raw_json["commit"]["record"]["reply"]["parent"]["uri"]: {
                "status": "available",
                "author": {"displayName": "Someone", "handle": "someone.bsky.social", "avatarUrl": None},
                "text": "the context text",
                "createdAt": "2026-09-20T00:00:00Z",
            }},
            {post.raw_json["commit"]["record"]["reply"]["parent"]["uri"]: "did:plc:parent-author"},
        ),
    )
    # own text scores lower than the target -- min() should pick the own score
    monkeypatch.setattr(pipeline.quality_model, "score_batch", lambda texts: {t.id: 0.5 if t.text == "Yumm!" else 0.9 for t in texts})
    monkeypatch.setattr(pipeline.political_model, "score_batch", lambda texts: {t.id: 0.1 for t in texts})
    monkeypatch.setattr(pipeline.political_centroid, "score_batch", lambda texts: {t.id: 0.001 for t in texts})

    deleted = []
    monkeypatch.setattr(pipeline.db, "delete_raw_post", lambda post_id: deleted.append(post_id))
    applied = []
    monkeypatch.setattr(pipeline.db, "apply_context_resolution", lambda resolutions: applied.extend(resolutions))

    assert pipeline.resolve_context() == 0
    assert deleted == []
    assert len(applied) == 1
    result = applied[0]
    assert result.raw_post_id == "reply-id"
    assert result.quality_score == 0.5  # min(0.5, 0.9)
    assert result.context_content["text"] == "the context text"
    # created_at ~ now, so recency_decay ~ 1.0
    assert result.base_score == pytest.approx(0.5, rel=1e-4)


def test_resolve_context_filtered_target_excludes_post(monkeypatch):
    post = _reply_post()
    parent_uri = post.raw_json["commit"]["record"]["reply"]["parent"]["uri"]
    monkeypatch.setattr(pipeline.db, "fetch_context_pending", lambda batch_size: [post])
    _stub_moderation(monkeypatch)
    _stub_permissive_filters(monkeypatch)
    monkeypatch.setattr(
        pipeline.quote_resolver,
        "resolve_context",
        lambda uris, terms, domains: ({parent_uri: {"status": "unavailable", "reason": "filtered"}}, {}),
    )
    monkeypatch.setattr(pipeline.quality_model, "score_batch", lambda texts: {t.id: 0.9 for t in texts})

    deleted = []
    monkeypatch.setattr(pipeline.db, "delete_raw_post", lambda post_id: deleted.append(post_id))
    applied = []
    monkeypatch.setattr(pipeline.db, "apply_context_resolution", lambda resolutions: applied.extend(resolutions))

    assert pipeline.resolve_context() == 1
    assert deleted == ["reply-id"]
    assert applied == []


def test_resolve_context_not_found_falls_back_to_standalone_own_score(monkeypatch):
    post = _reply_post()
    parent_uri = post.raw_json["commit"]["record"]["reply"]["parent"]["uri"]
    monkeypatch.setattr(pipeline.db, "fetch_context_pending", lambda batch_size: [post])
    _stub_moderation(monkeypatch)
    _stub_permissive_filters(monkeypatch)
    monkeypatch.setattr(
        pipeline.quote_resolver,
        "resolve_context",
        lambda uris, terms, domains: ({parent_uri: {"status": "unavailable", "reason": "not_found"}}, {}),
    )
    monkeypatch.setattr(pipeline.quality_model, "score_batch", lambda texts: {t.id: 0.6 for t in texts})

    deleted = []
    monkeypatch.setattr(pipeline.db, "delete_raw_post", lambda post_id: deleted.append(post_id))
    applied = []
    monkeypatch.setattr(pipeline.db, "apply_context_resolution", lambda resolutions: applied.extend(resolutions))

    assert pipeline.resolve_context() == 0
    assert deleted == []
    assert len(applied) == 1
    assert applied[0].quality_score == 0.6
    assert applied[0].context_content is None  # written as context_status = 'unavailable'
    # The standalone-fallback path must still get a real base_score, not
    # the stale 0.0 from the first pending pass -- issue #299.
    assert applied[0].base_score == pytest.approx(0.6, rel=1e-4)


def test_resolve_context_non_english_target_excludes_post(monkeypatch):
    post = _reply_post()
    parent_uri = post.raw_json["commit"]["record"]["reply"]["parent"]["uri"]
    monkeypatch.setattr(pipeline.db, "fetch_context_pending", lambda batch_size: [post])
    _stub_moderation(monkeypatch)
    _stub_permissive_filters(monkeypatch)
    monkeypatch.setattr(pipeline.language_filter, "is_non_english", lambda text: True)
    monkeypatch.setattr(
        pipeline.quote_resolver,
        "resolve_context",
        lambda uris, terms, domains: (
            {parent_uri: {"status": "available", "author": {}, "text": "texte non anglais", "createdAt": None}},
            {},
        ),
    )
    monkeypatch.setattr(pipeline.quality_model, "score_batch", lambda texts: {t.id: 0.9 for t in texts})
    monkeypatch.setattr(pipeline.political_model, "score_batch", lambda texts: {})
    monkeypatch.setattr(pipeline.political_centroid, "score_batch", lambda texts: {})

    deleted = []
    monkeypatch.setattr(pipeline.db, "delete_raw_post", lambda post_id: deleted.append(post_id))
    monkeypatch.setattr(pipeline.db, "apply_context_resolution", lambda resolutions: None)

    assert pipeline.resolve_context() == 1
    assert deleted == ["reply-id"]


def test_resolve_context_political_target_excludes_post(monkeypatch):
    post = _reply_post()
    parent_uri = post.raw_json["commit"]["record"]["reply"]["parent"]["uri"]
    monkeypatch.setattr(pipeline.db, "fetch_context_pending", lambda batch_size: [post])
    _stub_moderation(monkeypatch)
    _stub_permissive_filters(monkeypatch)
    monkeypatch.setattr(pipeline.political_exclude, "is_political_excluded", lambda c, s: True)
    monkeypatch.setattr(
        pipeline.quote_resolver,
        "resolve_context",
        lambda uris, terms, domains: (
            {parent_uri: {"status": "available", "author": {}, "text": "political text", "createdAt": None}},
            {},
        ),
    )
    monkeypatch.setattr(pipeline.quality_model, "score_batch", lambda texts: {t.id: 0.9 for t in texts})
    monkeypatch.setattr(pipeline.political_model, "score_batch", lambda texts: {t.id: 0.9 for t in texts})
    monkeypatch.setattr(pipeline.political_centroid, "score_batch", lambda texts: {t.id: 0.9 for t in texts})

    deleted = []
    monkeypatch.setattr(pipeline.db, "delete_raw_post", lambda post_id: deleted.append(post_id))
    monkeypatch.setattr(pipeline.db, "apply_context_resolution", lambda resolutions: None)

    assert pipeline.resolve_context() == 1
    assert deleted == ["reply-id"]


def test_resolve_context_bot_author_target_excludes_post(monkeypatch):
    post = _reply_post()
    parent_uri = post.raw_json["commit"]["record"]["reply"]["parent"]["uri"]
    monkeypatch.setattr(pipeline.db, "fetch_context_pending", lambda batch_size: [post])
    _stub_moderation(monkeypatch)
    _stub_permissive_filters(monkeypatch)
    monkeypatch.setattr(pipeline.db, "recent_bot_verdict", lambda source, author_id: author_id == "did:plc:bot-author")
    monkeypatch.setattr(
        pipeline.quote_resolver,
        "resolve_context",
        lambda uris, terms, domains: (
            {parent_uri: {"status": "available", "author": {}, "text": "spam spam spam", "createdAt": None}},
            {parent_uri: "did:plc:bot-author"},
        ),
    )
    monkeypatch.setattr(pipeline.quality_model, "score_batch", lambda texts: {t.id: 0.9 for t in texts})
    monkeypatch.setattr(pipeline.political_model, "score_batch", lambda texts: {t.id: 0.1 for t in texts})
    monkeypatch.setattr(pipeline.political_centroid, "score_batch", lambda texts: {t.id: 0.001 for t in texts})

    deleted = []
    monkeypatch.setattr(pipeline.db, "delete_raw_post", lambda post_id: deleted.append(post_id))
    monkeypatch.setattr(pipeline.db, "apply_context_resolution", lambda resolutions: None)

    assert pipeline.resolve_context() == 1
    assert deleted == ["reply-id"]


def test_resolve_context_resolves_mastodon_target(monkeypatch):
    post = _mastodon_reply_post()
    target = "mastodon.example/42"
    monkeypatch.setattr(pipeline.db, "fetch_context_pending", lambda batch_size: [post])
    _stub_moderation(monkeypatch)
    _stub_permissive_filters(monkeypatch)

    # Bluesky resolver must not be called with a Mastodon-shaped target.
    monkeypatch.setattr(
        pipeline.quote_resolver,
        "resolve_context",
        lambda targets, terms, domains: ({}, {}) if targets == [] else (_ for _ in ()).throw(AssertionError(targets)),
    )
    monkeypatch.setattr(
        pipeline.mastodon_resolver,
        "resolve_context",
        lambda targets, terms, domains: (
            {target: {
                "status": "available",
                "author": {"displayName": "Someone", "handle": "someone@mastodon.example", "avatarUrl": None},
                "text": "the parent status text",
                "createdAt": "2026-09-20T00:00:00Z",
            }},
            {target: "someone@mastodon.example"},
        ),
    )
    monkeypatch.setattr(pipeline.quality_model, "score_batch", lambda texts: {t.id: 0.5 if t.text == "Yumm!" else 0.9 for t in texts})
    monkeypatch.setattr(pipeline.political_model, "score_batch", lambda texts: {t.id: 0.1 for t in texts})
    monkeypatch.setattr(pipeline.political_centroid, "score_batch", lambda texts: {t.id: 0.001 for t in texts})

    deleted = []
    monkeypatch.setattr(pipeline.db, "delete_raw_post", lambda post_id: deleted.append(post_id))
    applied = []
    monkeypatch.setattr(pipeline.db, "apply_context_resolution", lambda resolutions: applied.extend(resolutions))

    assert pipeline.resolve_context() == 0
    assert deleted == []
    assert len(applied) == 1
    result = applied[0]
    assert result.raw_post_id == "masto-reply-id"
    assert result.quality_score == 0.5  # min(0.5, 0.9)
    assert result.context_content["text"] == "the parent status text"
    assert result.base_score == pytest.approx(0.5, rel=1e-4)


def test_resolve_context_mastodon_target_bot_author_uses_mastodon_source(monkeypatch):
    post = _mastodon_reply_post()
    target = "mastodon.example/42"
    monkeypatch.setattr(pipeline.db, "fetch_context_pending", lambda batch_size: [post])
    _stub_moderation(monkeypatch)
    _stub_permissive_filters(monkeypatch)

    seen_sources = []

    def _recent_bot_verdict(source, author_id):
        seen_sources.append(source)
        return author_id == "spammer@mastodon.example"

    monkeypatch.setattr(pipeline.db, "recent_bot_verdict", _recent_bot_verdict)
    monkeypatch.setattr(pipeline.quote_resolver, "resolve_context", lambda targets, terms, domains: ({}, {}))
    monkeypatch.setattr(
        pipeline.mastodon_resolver,
        "resolve_context",
        lambda targets, terms, domains: (
            {target: {"status": "available", "author": {}, "text": "spam spam spam", "createdAt": None}},
            {target: "spammer@mastodon.example"},
        ),
    )
    monkeypatch.setattr(pipeline.quality_model, "score_batch", lambda texts: {t.id: 0.9 for t in texts})
    monkeypatch.setattr(pipeline.political_model, "score_batch", lambda texts: {t.id: 0.1 for t in texts})
    monkeypatch.setattr(pipeline.political_centroid, "score_batch", lambda texts: {t.id: 0.001 for t in texts})

    deleted = []
    monkeypatch.setattr(pipeline.db, "delete_raw_post", lambda post_id: deleted.append(post_id))
    monkeypatch.setattr(pipeline.db, "apply_context_resolution", lambda resolutions: None)

    assert pipeline.resolve_context() == 1
    assert deleted == ["masto-reply-id"]
    # The target's own platform (mastodon), not post.source, which happens
    # to be mastodon here too -- the real discriminator is exercised by the
    # mixed-batch test below.
    assert seen_sources == ["mastodon"]


def test_resolve_context_mixed_batch_dispatches_by_target_shape(monkeypatch):
    bsky_post = _reply_post(raw_post_id="bsky-reply-id", parent_uri="at://did:plc:parent/app.bsky.feed.post/p1")
    masto_post = _mastodon_reply_post(raw_post_id="masto-reply-id")
    masto_target = "mastodon.example/42"
    bsky_target = "at://did:plc:parent/app.bsky.feed.post/p1"

    monkeypatch.setattr(pipeline.db, "fetch_context_pending", lambda batch_size: [bsky_post, masto_post])
    _stub_moderation(monkeypatch)
    _stub_permissive_filters(monkeypatch)

    bsky_calls = []
    masto_calls = []

    def _bsky_resolve(targets, terms, domains):
        bsky_calls.append(list(targets))
        return (
            {bsky_target: {"status": "available", "author": {}, "text": "bsky parent text", "createdAt": None}},
            {},
        )

    def _masto_resolve(targets, terms, domains):
        masto_calls.append(list(targets))
        return (
            {masto_target: {"status": "available", "author": {}, "text": "masto parent text", "createdAt": None}},
            {},
        )

    monkeypatch.setattr(pipeline.quote_resolver, "resolve_context", _bsky_resolve)
    monkeypatch.setattr(pipeline.mastodon_resolver, "resolve_context", _masto_resolve)
    monkeypatch.setattr(pipeline.quality_model, "score_batch", lambda texts: {t.id: 0.9 for t in texts})
    monkeypatch.setattr(pipeline.political_model, "score_batch", lambda texts: {t.id: 0.1 for t in texts})
    monkeypatch.setattr(pipeline.political_centroid, "score_batch", lambda texts: {t.id: 0.001 for t in texts})

    applied = []
    monkeypatch.setattr(pipeline.db, "delete_raw_post", lambda post_id: None)
    monkeypatch.setattr(pipeline.db, "apply_context_resolution", lambda resolutions: applied.extend(resolutions))

    assert pipeline.resolve_context() == 0
    assert bsky_calls == [[bsky_target]]
    assert masto_calls == [[masto_target]]
    assert {r.raw_post_id for r in applied} == {"bsky-reply-id", "masto-reply-id"}
    for r in applied:
        assert r.base_score == pytest.approx(0.9, rel=1e-4)  # min(0.9, 0.9)


def test_resolve_context_combined_score_below_threshold_excludes_post(monkeypatch):
    post = _reply_post()
    parent_uri = post.raw_json["commit"]["record"]["reply"]["parent"]["uri"]
    monkeypatch.setattr(pipeline.db, "fetch_context_pending", lambda batch_size: [post])
    _stub_moderation(monkeypatch)
    _stub_permissive_filters(monkeypatch)
    # the combined min() dips below threshold even though the target alone looked fine
    monkeypatch.setattr(pipeline.quality_exclude, "is_quality_excluded", lambda score: score < 0.4)
    monkeypatch.setattr(
        pipeline.quote_resolver,
        "resolve_context",
        lambda uris, terms, domains: (
            {parent_uri: {"status": "available", "author": {}, "text": "fine on its own", "createdAt": None}},
            {},
        ),
    )
    monkeypatch.setattr(pipeline.quality_model, "score_batch", lambda texts: {t.id: 0.2 if t.text == "Yumm!" else 0.8 for t in texts})
    monkeypatch.setattr(pipeline.political_model, "score_batch", lambda texts: {t.id: 0.1 for t in texts})
    monkeypatch.setattr(pipeline.political_centroid, "score_batch", lambda texts: {t.id: 0.001 for t in texts})

    deleted = []
    monkeypatch.setattr(pipeline.db, "delete_raw_post", lambda post_id: deleted.append(post_id))
    monkeypatch.setattr(pipeline.db, "apply_context_resolution", lambda resolutions: None)

    assert pipeline.resolve_context() == 1
    assert deleted == ["reply-id"]
