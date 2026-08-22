import requests

from infra.db import UncheckedBlueskyPost
from pipeline_stages import moderation_recheck


class FakeResponse:
    def __init__(self, payload=None, status_error=None):
        self._payload = payload
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error

    def json(self):
        return self._payload


def post_view(uri, post_labels=None, author_labels=None):
    return {
        "uri": uri,
        "author": {"did": "did:plc:abc", "labels": [{"val": v} for v in (author_labels or [])]},
        "record": {"text": "hello"},
        "labels": [{"val": v} for v in (post_labels or [])],
        "likeCount": 9999,  # must never influence the result
        "repostCount": 9999,
    }


def unchecked(raw_post_id, source_id):
    return UncheckedBlueskyPost(raw_post_id=raw_post_id, source_id=source_id, author_id="did:plc:abc")


def test_post_uri_round_trips_source_id():
    assert moderation_recheck._post_uri("did:plc:abc/3xyz") == "at://did:plc:abc/app.bsky.feed.post/3xyz"


def test_check_posts_post_level_label_is_excluded(monkeypatch):
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse({"posts": [post_view(uri, post_labels=["porn"])]}))

    result = moderation_recheck.check_posts([unchecked("id1", "did:plc:abc/xyz")])

    assert result == {"id1": "excluded"}


def test_check_posts_author_profile_label_is_excluded(monkeypatch):
    # postView.author.labels (the account's own profile self-label) is a
    # separate signal from postView.labels (the post's own moderation
    # labels) -- neither incident this backstop was built for had this,
    # but it's a real, separately-confirmed gap nothing else checks.
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: FakeResponse({"posts": [post_view(uri, author_labels=["nudity"])]})
    )

    result = moderation_recheck.check_posts([unchecked("id1", "did:plc:abc/xyz")])

    assert result == {"id1": "excluded"}


def test_check_posts_no_labels_is_clean(monkeypatch):
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse({"posts": [post_view(uri)]}))

    result = moderation_recheck.check_posts([unchecked("id1", "did:plc:abc/xyz")])

    assert result == {"id1": "clean"}


def test_check_posts_uri_absent_from_response_is_clean(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse({"posts": []}))

    result = moderation_recheck.check_posts([unchecked("id1", "did:plc:abc/xyz")])

    assert result == {"id1": "clean"}


def test_check_posts_failing_batch_omits_its_posts(monkeypatch):
    def raise_error(*a, **k):
        raise requests.ConnectionError("network unreachable")

    monkeypatch.setattr(requests, "get", raise_error)

    result = moderation_recheck.check_posts([unchecked("id1", "did:plc:abc/xyz")])  # must not raise

    assert result == {}


def test_check_posts_batches_at_25_uri_boundary(monkeypatch):
    posts = [unchecked(f"id{i}", f"did:plc:abc/{i}") for i in range(30)]
    calls = []

    def fake_get(url, params, timeout):
        calls.append(params)
        batch_uris = [v for _, v in params]
        return FakeResponse({"posts": [post_view(u) for u in batch_uris]})

    monkeypatch.setattr(requests, "get", fake_get)

    result = moderation_recheck.check_posts(posts)

    assert len(calls) == 2
    assert len(calls[0]) == 25
    assert len(calls[1]) == 5
    assert all(result[f"id{i}"] == "clean" for i in range(30))
