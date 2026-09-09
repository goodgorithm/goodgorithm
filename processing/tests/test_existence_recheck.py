import requests

from infra.db import ExistenceCheckPost
from pipeline_stages import existence_recheck


class FakeResponse:
    def __init__(self, payload=None, status_error=None):
        self._payload = payload
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error

    def json(self):
        return self._payload


def post_view(uri):
    return {
        "uri": uri,
        "author": {"did": "did:plc:abc"},
        "record": {"text": "hello"},
        "likeCount": 9999,  # must never influence the result
        "repostCount": 9999,
    }


def to_check(raw_post_id, source_id):
    return ExistenceCheckPost(raw_post_id=raw_post_id, source_id=source_id)


def test_post_uri_round_trips_source_id():
    assert existence_recheck._post_uri("did:plc:abc/3xyz") == "at://did:plc:abc/app.bsky.feed.post/3xyz"


def test_check_existence_present_post_is_present(monkeypatch):
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse({"posts": [post_view(uri)]}))

    result = existence_recheck.check_existence([to_check("id1", "did:plc:abc/xyz")])

    assert result == {"id1": "present"}


def test_check_existence_uri_absent_from_successful_response_is_gone(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse({"posts": []}))

    result = existence_recheck.check_existence([to_check("id1", "did:plc:abc/xyz")])

    assert result == {"id1": "gone"}


def test_check_existence_mixed_batch_reports_each_uri(monkeypatch):
    present_uri = "at://did:plc:abc/app.bsky.feed.post/live"
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse({"posts": [post_view(present_uri)]}))

    result = existence_recheck.check_existence(
        [to_check("id_live", "did:plc:abc/live"), to_check("id_dead", "did:plc:abc/dead")]
    )

    assert result == {"id_live": "present", "id_dead": "gone"}


def test_check_existence_failing_batch_omits_its_posts(monkeypatch):
    def raise_error(*a, **k):
        raise requests.ConnectionError("network unreachable")

    monkeypatch.setattr(requests, "get", raise_error)

    result = existence_recheck.check_existence([to_check("id1", "did:plc:abc/xyz")])  # must not raise

    assert result == {}


def test_check_existence_batches_at_25_uri_boundary(monkeypatch):
    posts = [to_check(f"id{i}", f"did:plc:abc/{i}") for i in range(30)]
    calls = []

    def fake_get(url, params, timeout):
        calls.append(params)
        batch_uris = [v for _, v in params]
        return FakeResponse({"posts": [post_view(u) for u in batch_uris]})

    monkeypatch.setattr(requests, "get", fake_get)

    result = existence_recheck.check_existence(posts)

    assert len(calls) == 2
    assert len(calls[0]) == 25
    assert len(calls[1]) == 5
    assert all(result[f"id{i}"] == "present" for i in range(30))
