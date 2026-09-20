import requests

from pipeline_stages import quote_resolver

TERMS = frozenset({"nsfw"})
DOMAINS = frozenset({"amazon.com"})

# --- extract_quote_uri ---


def test_extract_quote_uri_direct_quote():
    raw_json = {
        "commit": {
            "record": {
                "embed": {
                    "$type": "app.bsky.embed.record",
                    "record": {"cid": "x", "uri": "at://did:plc:abc/app.bsky.feed.post/xyz"},
                }
            }
        }
    }
    assert quote_resolver.extract_quote_uri(raw_json) == "at://did:plc:abc/app.bsky.feed.post/xyz"


def test_extract_quote_uri_record_with_media_nesting():
    # The quote is at embed.record.record, not embed.record directly.
    raw_json = {
        "commit": {
            "record": {
                "embed": {
                    "$type": "app.bsky.embed.recordWithMedia",
                    "media": {"$type": "app.bsky.embed.images", "images": []},
                    "record": {
                        "$type": "app.bsky.embed.record",
                        "record": {"cid": "x", "uri": "at://did:plc:abc/app.bsky.feed.post/xyz"},
                    },
                }
            }
        }
    }
    assert quote_resolver.extract_quote_uri(raw_json) == "at://did:plc:abc/app.bsky.feed.post/xyz"


def test_extract_quote_uri_non_post_collection_is_skipped():
    raw_json = {
        "commit": {
            "record": {
                "embed": {
                    "$type": "app.bsky.embed.record",
                    "record": {"cid": "x", "uri": "at://did:plc:abc/app.bsky.graph.list/xyz"},
                }
            }
        }
    }
    assert quote_resolver.extract_quote_uri(raw_json) is None


def test_extract_quote_uri_no_embed_or_non_quote_embed():
    assert quote_resolver.extract_quote_uri({"commit": {"record": {}}}) is None
    assert quote_resolver.extract_quote_uri(
        {"commit": {"record": {"embed": {"$type": "app.bsky.embed.images", "images": []}}}}
    ) is None


def test_extract_quote_uri_mastodon_rows_have_no_commit_key():
    assert quote_resolver.extract_quote_uri({"id": "123", "content": "<p>hi</p>"}) is None


def test_extract_quote_uri_is_defensive_about_malformed_shapes():
    assert quote_resolver.extract_quote_uri({}) is None
    assert quote_resolver.extract_quote_uri(None) is None
    assert quote_resolver.extract_quote_uri({"commit": {"record": {"embed": "not-a-dict"}}}) is None
    assert (
        quote_resolver.extract_quote_uri(
            {"commit": {"record": {"embed": {"$type": "app.bsky.embed.recordWithMedia", "record": "not-a-dict"}}}}
        )
        is None
    )


# --- extract_reply_parent_uri ---


def test_extract_reply_parent_uri_present():
    raw_json = {
        "commit": {
            "record": {"reply": {"parent": {"uri": "at://did:plc:abc/app.bsky.feed.post/xyz", "cid": "x"}}}
        }
    }
    assert quote_resolver.extract_reply_parent_uri(raw_json) == "at://did:plc:abc/app.bsky.feed.post/xyz"


def test_extract_reply_parent_uri_absent():
    assert quote_resolver.extract_reply_parent_uri({"commit": {"record": {}}}) is None
    assert quote_resolver.extract_reply_parent_uri({}) is None
    assert quote_resolver.extract_reply_parent_uri(None) is None


# --- extract_context_target ---


def test_extract_context_target_prefers_quote_over_reply():
    raw_json = {
        "commit": {
            "record": {
                "embed": {
                    "$type": "app.bsky.embed.record",
                    "record": {"cid": "x", "uri": "at://did:plc:quote/app.bsky.feed.post/q"},
                },
                "reply": {"parent": {"uri": "at://did:plc:reply/app.bsky.feed.post/r"}},
            }
        }
    }
    assert quote_resolver.extract_context_target(raw_json) == ("quote", "at://did:plc:quote/app.bsky.feed.post/q")


def test_extract_context_target_reply_when_no_quote():
    raw_json = {"commit": {"record": {"reply": {"parent": {"uri": "at://did:plc:reply/app.bsky.feed.post/r"}}}}}
    assert quote_resolver.extract_context_target(raw_json) == ("reply", "at://did:plc:reply/app.bsky.feed.post/r")


def test_extract_context_target_none_when_neither():
    assert quote_resolver.extract_context_target({"commit": {"record": {}}}) is None


# --- resolve_context ---


class FakeResponse:
    def __init__(self, payload=None, status_error=None):
        self._payload = payload
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error

    def json(self):
        return self._payload


def post_view(uri, text, display_name="Someone", handle="someone.bsky.social", labels=None, self_labels=None, did="did:plc:author"):
    record = {"text": text, "createdAt": "2026-08-10T12:00:00Z"}
    if self_labels is not None:
        record["labels"] = {"values": [{"val": v} for v in self_labels]}
    return {
        "uri": uri,
        "author": {"did": did, "displayName": display_name, "handle": handle, "avatar": "https://example.com/a.jpg"},
        "record": record,
        "labels": [{"val": v} for v in (labels or [])],
        "likeCount": 9999,  # must never surface in the mapped output
        "repostCount": 9999,
    }


def test_resolve_context_maps_a_resolvable_post(monkeypatch):
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: FakeResponse({"posts": [post_view(uri, "a lovely post")]})
    )

    result, author_dids = quote_resolver.resolve_context([uri], TERMS, DOMAINS)

    assert result[uri]["status"] == "available"
    assert result[uri]["text"] == "a lovely post"
    assert result[uri]["author"] == {
        "displayName": "Someone",
        "handle": "someone.bsky.social",
        "avatarUrl": "https://example.com/a.jpg",
    }
    assert result[uri]["createdAt"] == "2026-08-10T12:00:00Z"
    assert result[uri]["url"] == "https://bsky.app/profile/did:plc:abc/post/xyz"
    # engagement counts must never leak into the mapped shape
    assert "likeCount" not in result[uri]
    assert "repostCount" not in result[uri]
    assert author_dids[uri] == "did:plc:author"


def test_resolve_context_uri_absent_from_response_is_not_found(monkeypatch):
    uri = "at://did:plc:abc/app.bsky.feed.post/deleted"
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse({"posts": []}))

    result, author_dids = quote_resolver.resolve_context([uri], TERMS, DOMAINS)

    assert result[uri] == {"status": "unavailable", "reason": "not_found"}
    assert uri not in author_dids


def test_resolve_context_hashtag_match_is_filtered(monkeypatch):
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: FakeResponse({"posts": [post_view(uri, "check this out #nsfw")]})
    )

    result, _ = quote_resolver.resolve_context([uri], TERMS, DOMAINS)

    assert result[uri] == {"status": "unavailable", "reason": "filtered"}


def test_resolve_context_domain_match_is_filtered(monkeypatch):
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: FakeResponse(
            {"posts": [post_view(uri, "check this out https://amazon.com/dp/B00123")]}
        ),
    )

    result, _ = quote_resolver.resolve_context([uri], TERMS, DOMAINS)

    assert result[uri] == {"status": "unavailable", "reason": "filtered"}


def test_resolve_context_self_label_match_is_filtered(monkeypatch):
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: FakeResponse({"posts": [post_view(uri, "a normal caption", self_labels=["sexual"])]}),
    )

    result, _ = quote_resolver.resolve_context([uri], TERMS, DOMAINS)

    assert result[uri] == {"status": "unavailable", "reason": "filtered"}


def test_resolve_context_moderation_label_match_is_filtered(monkeypatch):
    # postView.labels (externally-applied moderation labels, e.g. from
    # mod.bsky.app) is distinct from record.labels (self-labels) - both
    # must independently trigger filtering.
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: FakeResponse({"posts": [post_view(uri, "a normal caption", labels=["porn"])]}),
    )

    result, _ = quote_resolver.resolve_context([uri], TERMS, DOMAINS)

    assert result[uri] == {"status": "unavailable", "reason": "filtered"}


def test_resolve_context_batches_at_25_uri_boundary(monkeypatch):
    uris = [f"at://did:plc:abc/app.bsky.feed.post/{i}" for i in range(30)]
    calls = []

    def fake_get(url, params, timeout):
        calls.append(params)
        batch_uris = [v for _, v in params]
        return FakeResponse({"posts": [post_view(u, f"post {u}") for u in batch_uris]})

    monkeypatch.setattr(requests, "get", fake_get)

    result, _ = quote_resolver.resolve_context(uris, TERMS, DOMAINS)

    assert len(calls) == 2
    assert len(calls[0]) == 25
    assert len(calls[1]) == 5
    assert all(result[uri]["status"] == "available" for uri in uris)


def test_resolve_context_dedupes_repeated_uris(monkeypatch):
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
    calls = []

    def fake_get(url, params, timeout):
        calls.append(params)
        return FakeResponse({"posts": [post_view(uri, "hello")]})

    monkeypatch.setattr(requests, "get", fake_get)

    quote_resolver.resolve_context([uri, uri, uri], TERMS, DOMAINS)

    assert len(calls) == 1
    assert len(calls[0]) == 1


def test_resolve_context_network_failure_omits_uris_entirely(monkeypatch):
    # A failed batch must never crash the calling cycle - the caller
    # treats an absent key the same as an unresolved target.
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"

    def raise_error(*a, **k):
        raise requests.ConnectionError("network unreachable")

    monkeypatch.setattr(requests, "get", raise_error)

    result, author_dids = quote_resolver.resolve_context([uri], TERMS, DOMAINS)  # must not raise

    assert uri not in result
    assert uri not in author_dids


def test_resolve_context_http_error_status_omits_uris_entirely(monkeypatch):
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: FakeResponse(status_error=requests.HTTPError("429 rate limited")),
    )

    result, _ = quote_resolver.resolve_context([uri], TERMS, DOMAINS)  # must not raise

    assert uri not in result


def test_resolve_context_empty_input_makes_no_requests(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(1))

    result, author_dids = quote_resolver.resolve_context([], TERMS, DOMAINS)

    assert result == {}
    assert author_dids == {}
    assert calls == []
