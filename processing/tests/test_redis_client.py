from unittest.mock import MagicMock, patch

from infra import redis_client


def _make_client(monkeypatch):
    """Fresh _CompatClient wrapping a mocked redis-py connection, bypassing
    the module-level singleton so each test gets its own mock."""
    monkeypatch.setattr(redis_client, "_client", None)
    fake_conn = MagicMock()
    with patch.object(redis_client.redis_py.Redis, "from_url", return_value=fake_conn):
        client = redis_client.get_client()
    return client, fake_conn


def test_get_client_uses_redis_url_and_decode_responses(monkeypatch):
    monkeypatch.setattr(redis_client, "_client", None)
    monkeypatch.setattr(redis_client.config, "REDIS_URL", "redis://example:6379/0")
    with patch.object(redis_client.redis_py.Redis, "from_url") as from_url:
        redis_client.get_client()
    from_url.assert_called_once_with("redis://example:6379/0", decode_responses=True)


def test_get_client_is_a_singleton(monkeypatch):
    client, _ = _make_client(monkeypatch)
    assert redis_client.get_client() is client


def test_bare_client_execute_dispatches_raw_command(monkeypatch):
    client, fake_conn = _make_client(monkeypatch)
    fake_conn.execute_command.return_value = 42

    result = client.execute(["DBSIZE"])

    fake_conn.execute_command.assert_called_once_with("DBSIZE")
    assert result == 42


def test_bare_client_scan_passes_through_and_returns_tuple(monkeypatch):
    client, fake_conn = _make_client(monkeypatch)
    fake_conn.scan.return_value = (0, ["a", "b"])

    result = client.scan(5, match="foo:*", count=100)

    fake_conn.scan.assert_called_once_with(cursor=5, match="foo:*", count=100)
    assert result == (0, ["a", "b"])


def test_bare_client_delete_is_variadic(monkeypatch):
    client, fake_conn = _make_client(monkeypatch)
    fake_conn.delete.return_value = 2

    result = client.delete("a", "b")

    fake_conn.delete.assert_called_once_with("a", "b")
    assert result == 2


def test_pipeline_execute_queues_raw_command_and_returns_self(monkeypatch):
    client, fake_conn = _make_client(monkeypatch)
    fake_pipe = MagicMock()
    fake_conn.pipeline.return_value = fake_pipe

    pipe = client.pipeline()
    returned = pipe.execute(["MEMORY", "USAGE", "mh:1"])

    fake_pipe.execute_command.assert_called_once_with("MEMORY", "USAGE", "mh:1")
    fake_pipe.execute.assert_not_called()
    assert returned is pipe


def test_pipeline_exec_runs_the_queue(monkeypatch):
    client, fake_conn = _make_client(monkeypatch)
    fake_pipe = MagicMock()
    fake_pipe.execute.return_value = [1, True, 2, True]
    fake_conn.pipeline.return_value = fake_pipe

    pipe = client.pipeline()
    results = pipe.exec()

    fake_pipe.execute.assert_called_once_with()
    assert results == [1, True, 2, True]


def test_pipeline_named_methods_delegate_with_expected_kwargs(monkeypatch):
    client, fake_conn = _make_client(monkeypatch)
    fake_pipe = MagicMock()
    fake_conn.pipeline.return_value = fake_pipe

    pipe = client.pipeline()
    assert pipe.get("k") is pipe
    assert pipe.set("k", "v", ex=60) is pipe
    assert pipe.incr("k") is pipe
    assert pipe.expire("k", 60, nx=True) is pipe
    assert pipe.sadd("k", "a", "b") is pipe
    assert pipe.smembers("k") is pipe

    fake_pipe.get.assert_called_once_with("k")
    fake_pipe.set.assert_called_once_with("k", "v", ex=60)
    fake_pipe.incr.assert_called_once_with("k")
    fake_pipe.expire.assert_called_once_with("k", 60, nx=True)
    fake_pipe.sadd.assert_called_once_with("k", "a", "b")
    fake_pipe.smembers.assert_called_once_with("k")


def test_pipeline_expire_defaults_nx_false(monkeypatch):
    client, fake_conn = _make_client(monkeypatch)
    fake_pipe = MagicMock()
    fake_conn.pipeline.return_value = fake_pipe

    client.pipeline().expire("k", 60)

    fake_pipe.expire.assert_called_once_with("k", 60, nx=False)
