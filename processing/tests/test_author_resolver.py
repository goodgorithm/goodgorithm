import requests

from infra.db import UnresolvedAuthorPost
from pipeline_stages import author_resolver


class FakeResponse:
    def __init__(self, payload=None, status_error=None):
        self._payload = payload
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error

    def json(self):
        return self._payload


def post_view(uri, display_name=None, avatar=None):
    author: dict = {"did": "did:plc:abc"}
    if display_name is not None:
        author["displayName"] = display_name
    if avatar is not None:
        author["avatar"] = avatar
    return {
        "uri": uri,
        "author": author,
        "record": {"text": "hello"},
        "likeCount": 9999,  # must never influence the result
        "repostCount": 9999,
    }


def unresolved(raw_post_id, source_id):
    return UnresolvedAuthorPost(raw_post_id=raw_post_id, source_id=source_id, author_id="did:plc:abc")


def test_post_uri_round_trips_source_id():
    assert author_resolver._post_uri("did:plc:abc/3xyz") == "at://did:plc:abc/app.bsky.feed.post/3xyz"


def test_resolve_authors_maps_display_name_and_avatar(monkeypatch):
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: FakeResponse(
            {"posts": [post_view(uri, display_name="Jane Doe", avatar="https://example.com/a.jpg")]}
        ),
    )

    result = author_resolver.resolve_authors([unresolved("id1", "did:plc:abc/xyz")])

    assert result == {"id1": {"displayName": "Jane Doe", "avatarUrl": "https://example.com/a.jpg"}}


def test_resolve_authors_handles_partial_data():
    # A real, common case -- not every account sets an avatar.
    author = {"did": "did:plc:abc", "displayName": "Jane Doe"}
    assert author_resolver._map_author(author) == {"displayName": "Jane Doe", "avatarUrl": None}


def test_resolve_authors_no_display_name_or_avatar_is_none(monkeypatch):
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse({"posts": [post_view(uri)]}))

    result = author_resolver.resolve_authors([unresolved("id1", "did:plc:abc/xyz")])

    assert result == {"id1": None}


def test_map_author_is_defensive_about_malformed_shapes():
    assert author_resolver._map_author(None) is None
    assert author_resolver._map_author("not-a-dict") is None
    assert author_resolver._map_author({}) is None
    assert author_resolver._map_author({"displayName": 123, "avatar": 456}) is None


def test_resolve_authors_uri_absent_from_response_is_none(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse({"posts": []}))

    result = author_resolver.resolve_authors([unresolved("id1", "did:plc:abc/xyz")])

    assert result == {"id1": None}


def test_resolve_authors_failing_batch_omits_its_posts(monkeypatch):
    def raise_error(*a, **k):
        raise requests.ConnectionError("network unreachable")

    monkeypatch.setattr(requests, "get", raise_error)

    result = author_resolver.resolve_authors([unresolved("id1", "did:plc:abc/xyz")])  # must not raise

    assert result == {}


def test_resolve_authors_batches_at_25_uri_boundary(monkeypatch):
    posts = [unresolved(f"id{i}", f"did:plc:abc/{i}") for i in range(30)]
    calls = []

    def fake_get(url, params, timeout):
        calls.append(params)
        batch_uris = [v for _, v in params]
        return FakeResponse({"posts": [post_view(u, display_name="Someone") for u in batch_uris]})

    monkeypatch.setattr(requests, "get", fake_get)

    result = author_resolver.resolve_authors(posts)

    assert len(calls) == 2
    assert len(calls[0]) == 25
    assert len(calls[1]) == 5
    assert all(result[f"id{i}"] == {"displayName": "Someone", "avatarUrl": None} for i in range(30))
