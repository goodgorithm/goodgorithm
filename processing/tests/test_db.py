from infra import db


def test_processed_posts_upsert_sql_skips_rows_whose_raw_post_vanished():
    # issue #128: a raw_post can be deleted (ingestion's adult-label backstop)
    # between run_cycle fetching it and this write. The upsert must drop such
    # a row from the batch in-SQL, not FK-violate and crash-loop the process
    # -- infra/db.py has no try/except by design. Guard against a future
    # "simplify back to a plain VALUES INSERT" losing this.
    sql = db._build_processed_posts_upsert_sql(3)
    assert "INSERT INTO processed_posts" in sql
    assert "FROM (VALUES" in sql  # INSERT ... SELECT, not INSERT ... VALUES
    assert "WHERE EXISTS (SELECT 1 FROM raw_posts r WHERE r.id = v.raw_post_id" in sql
    assert "ON CONFLICT (raw_post_id) DO UPDATE" in sql
    assert sql.count("%s") == 3 * 18  # rows x columns, param count still bounded per chunk


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
