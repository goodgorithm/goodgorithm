from infra import redis_client, redis_guard


def test_parse_used_memory_bytes_extracts_value():
    info = "# Memory\r\nused_memory:1073751787\r\nused_memory_human:1.02G\r\n"
    assert redis_guard.parse_used_memory_bytes(info) == 1073751787


def test_parse_used_memory_bytes_returns_none_when_absent():
    assert redis_guard.parse_used_memory_bytes("# Memory\r\nsomething_else:1\r\n") is None


def test_get_used_memory_bytes_returns_none_on_client_failure(monkeypatch):
    class RaisingClient:
        def execute(self, command):
            raise RuntimeError("network unreachable")

    monkeypatch.setattr(redis_client, "get_client", lambda: RaisingClient())

    assert redis_guard.get_used_memory_bytes() is None  # must not raise


def test_get_used_memory_bytes_parses_info_response(monkeypatch):
    class FakeClient:
        def execute(self, command):
            assert command == ["INFO", "memory"]
            return "# Memory\r\nused_memory:123456\r\n"

    monkeypatch.setattr(redis_client, "get_client", lambda: FakeClient())

    assert redis_guard.get_used_memory_bytes() == 123456


class PagedScanClient:
    """Test double for a Redis client's scan/delete, with a multi-page scan
    so pagination (not just a single call) is exercised."""

    def __init__(self, pages: dict[int, tuple[int, list[str]]]) -> None:
        self._pages = pages
        self.deleted: list[str] = []

    def scan(self, cursor, match=None, count=None):
        return self._pages[cursor]

    def delete(self, *keys: str) -> int:
        self.deleted.extend(keys)
        return len(keys)


def test_scan_delete_paginates_until_cursor_zero():
    client = PagedScanClient({0: (5, ["k1", "k2"]), 5: (0, ["k3"])})

    deleted = redis_guard._scan_delete(client, "burst:entity:*")

    assert deleted == 3
    assert client.deleted == ["k1", "k2", "k3"]


def test_scan_delete_skips_delete_call_on_empty_page():
    client = PagedScanClient({0: (0, [])})

    deleted = redis_guard._scan_delete(client, "burst:entity:*")

    assert deleted == 0
    assert client.deleted == []


def test_clear_expendable_data_covers_every_expendable_pattern(monkeypatch):
    keys_by_pattern = {
        "burst:entity:*": ["burst:entity:a", "burst:entity:b"],
        "cluster:*:authors": ["cluster:c1:authors"],
    }

    class FakeClient:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def scan(self, cursor, match=None, count=None):
            return 0, keys_by_pattern.get(match, [])

        def delete(self, *keys: str) -> int:
            self.deleted.extend(keys)
            return len(keys)

    fake = FakeClient()
    monkeypatch.setattr(redis_client, "get_client", lambda: fake)

    deleted = redis_guard.clear_expendable_data()

    assert deleted == 3
    assert set(fake.deleted) == {"burst:entity:a", "burst:entity:b", "cluster:c1:authors"}


def test_clear_expendable_data_never_touches_dedup_state(monkeypatch):
    # lsh:band:*/mh:*/dedup:cluster:* must never be cleared automatically --
    # silently losing dedup's own state would let duplicate content back
    # into the feed without anyone noticing, worse than the crash this
    # guard exists to prevent.
    for pattern in redis_guard.EXPENDABLE_KEY_PATTERNS:
        assert not pattern.startswith("lsh:band:")
        assert not pattern.startswith("mh:")
        assert not pattern.startswith("dedup:cluster:")


def test_enforce_noop_when_usage_unknown(monkeypatch):
    monkeypatch.setattr(redis_guard, "get_used_memory_bytes", lambda: None)
    calls = []
    monkeypatch.setattr(redis_guard, "clear_expendable_data", lambda: calls.append(1))

    redis_guard.enforce(max_bytes=1000, soft_limit_ratio=0.85)

    assert calls == []


def test_enforce_noop_below_soft_limit(monkeypatch):
    monkeypatch.setattr(redis_guard, "get_used_memory_bytes", lambda: 500)
    calls = []
    monkeypatch.setattr(redis_guard, "clear_expendable_data", lambda: calls.append(1))

    redis_guard.enforce(max_bytes=1000, soft_limit_ratio=0.85)

    assert calls == []


def test_enforce_clears_at_or_above_soft_limit(monkeypatch):
    monkeypatch.setattr(redis_guard, "get_used_memory_bytes", lambda: 900)
    calls = []
    monkeypatch.setattr(redis_guard, "clear_expendable_data", lambda: (calls.append(1), 42)[1])

    redis_guard.enforce(max_bytes=1000, soft_limit_ratio=0.85)

    assert calls == [1]


def test_enforce_swallows_clear_expendable_data_failures(monkeypatch):
    monkeypatch.setattr(redis_guard, "get_used_memory_bytes", lambda: 900)

    def raise_error():
        raise RuntimeError("scan failed")

    monkeypatch.setattr(redis_guard, "clear_expendable_data", raise_error)

    redis_guard.enforce(max_bytes=1000, soft_limit_ratio=0.85)  # must not raise
