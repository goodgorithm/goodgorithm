from infra import db


def _reset_moderation_cache(monkeypatch):
    monkeypatch.setattr(db, "_moderation_lists_cache", None)
    monkeypatch.setattr(db, "_moderation_lists_cached_at", 0.0)
    monkeypatch.setattr(db, "MODERATION_LISTS_REFRESH_SECONDS", 60)


def test_fetch_moderation_lists_caches_within_ttl(monkeypatch):
    _reset_moderation_cache(monkeypatch)

    calls = {"blocked": 0, "terms": 0, "domains": 0}
    monkeypatch.setattr(db, "fetch_blocked_authors", lambda: calls.__setitem__("blocked", calls["blocked"] + 1) or {("bluesky", "did:x")})
    monkeypatch.setattr(db, "fetch_suppressed_terms", lambda: calls.__setitem__("terms", calls["terms"] + 1) or frozenset({"nsfw"}))
    monkeypatch.setattr(
        db, "fetch_suppressed_domains", lambda: calls.__setitem__("domains", calls["domains"] + 1) or frozenset({"example.com"})
    )
    monkeypatch.setattr(db.time, "monotonic", lambda: 1000.0)

    first = db.fetch_moderation_lists()
    second = db.fetch_moderation_lists()

    assert first == second == ({("bluesky", "did:x")}, frozenset({"nsfw"}), frozenset({"example.com"}))
    assert calls == {"blocked": 1, "terms": 1, "domains": 1}


def test_fetch_moderation_lists_refetches_after_ttl_expires(monkeypatch):
    _reset_moderation_cache(monkeypatch)

    calls = {"n": 0}

    def fake_fetch_blocked():
        calls["n"] += 1
        return set()

    monkeypatch.setattr(db, "fetch_blocked_authors", fake_fetch_blocked)
    monkeypatch.setattr(db, "fetch_suppressed_terms", lambda: frozenset())
    monkeypatch.setattr(db, "fetch_suppressed_domains", lambda: frozenset())

    fake_now = [1000.0]
    monkeypatch.setattr(db.time, "monotonic", lambda: fake_now[0])

    db.fetch_moderation_lists()
    fake_now[0] += 61  # past MODERATION_LISTS_REFRESH_SECONDS
    db.fetch_moderation_lists()

    assert calls["n"] == 2
