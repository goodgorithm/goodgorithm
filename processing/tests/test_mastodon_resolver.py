import requests

from pipeline_stages import mastodon_resolver

TERMS = frozenset({"nsfw"})
DOMAINS = frozenset({"amazon.com"})


# --- extract_reply_target ---


def test_extract_reply_target_present():
    raw_json = {"in_reply_to_id": "42"}
    assert mastodon_resolver.extract_reply_target(raw_json, "mastodon.example/someone") == "mastodon.example/42"


def test_extract_reply_target_absent():
    assert mastodon_resolver.extract_reply_target({"in_reply_to_id": None}, "mastodon.example/someone") is None
    assert mastodon_resolver.extract_reply_target({}, "mastodon.example/someone") is None
    assert mastodon_resolver.extract_reply_target(None, "mastodon.example/someone") is None


def test_extract_reply_target_no_polled_instance_in_author_id():
    assert mastodon_resolver.extract_reply_target({"in_reply_to_id": "42"}, "") is None
    assert mastodon_resolver.extract_reply_target({"in_reply_to_id": "42"}, "/bare-local") is None


def test_extract_reply_target_uses_polled_instance_not_a_field_in_raw_json():
    # The polled instance only ever comes from author_id -- a status API
    # response never names which instance served it.
    raw_json = {"in_reply_to_id": "42", "instance": "not-the-right-instance.example"}
    assert (
        mastodon_resolver.extract_reply_target(raw_json, "mastodon.example/someone") == "mastodon.example/42"
    )


# --- resolve_context ---


class FakeResponse:
    def __init__(self, payload=None, status_code=200, status_error=None):
        self._payload = payload
        self.status_code = status_code
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error

    def json(self):
        return self._payload


def status_payload(
    content="<p>a lovely status</p>",
    display_name="Someone",
    acct="someone",
    avatar="https://example.com/a.jpg",
    sensitive=False,
    spoiler_text="",
    url="https://mastodon.example/@someone/42",
    discoverable=True,
    indexable=True,
    noindex=False,
    bot=False,
):
    return {
        "content": content,
        "created_at": "2026-08-10T12:00:00Z",
        "sensitive": sensitive,
        "spoiler_text": spoiler_text,
        "media_attachments": [],
        "account": {
            "display_name": display_name,
            "acct": acct,
            "username": acct,
            "avatar": avatar,
            "discoverable": discoverable,
            "indexable": indexable,
            "noindex": noindex,
            "bot": bot,
        },
        "favourites_count": 9999,  # must never surface in the mapped output
        "reblogs_count": 9999,
        "url": url,
    }


def test_resolve_context_maps_a_resolvable_status(monkeypatch):
    target = "mastodon.example/42"
    monkeypatch.setattr(requests, "get", lambda url, timeout, headers: FakeResponse(status_payload()))

    result, author_ids = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)

    assert result[target]["status"] == "available"
    assert result[target]["text"] == "a lovely status"
    assert result[target]["author"] == {
        "displayName": "Someone",
        "handle": "someone",
        "avatarUrl": "https://example.com/a.jpg",
    }
    assert result[target]["createdAt"] == "2026-08-10T12:00:00Z"
    assert result[target]["url"] == "https://mastodon.example/@someone/42"
    assert "favourites_count" not in result[target]
    assert "reblogs_count" not in result[target]
    # bare-local acct qualified with the target's own origin instance
    assert author_ids[target] == "someone@mastodon.example"


def test_resolve_context_missing_url_maps_to_none(monkeypatch):
    target = "mastodon.example/42"
    payload = status_payload()
    del payload["url"]
    monkeypatch.setattr(requests, "get", lambda url, timeout, headers: FakeResponse(payload))

    result, _ = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)

    assert result[target]["url"] is None


def test_resolve_context_strips_html_and_collapses_whitespace(monkeypatch):
    target = "mastodon.example/42"
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, timeout, headers: FakeResponse(
            status_payload(content="<p>Hello   <a href=\"x\">world</a></p><p>Second para</p>")
        ),
    )

    result, _ = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)

    assert result[target]["text"] == "Hello world Second para"


def test_resolve_context_already_qualified_acct_passes_through(monkeypatch):
    # A remote/federated account's acct is already user@host from the
    # polled instance's own point of view -- must not get double-qualified.
    target = "mastodon.example/42"
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, timeout, headers: FakeResponse(status_payload(acct="someone@another.example")),
    )

    _, author_ids = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)

    assert author_ids[target] == "someone@another.example"


def test_resolve_context_404_is_not_found(monkeypatch):
    target = "mastodon.example/deleted"
    monkeypatch.setattr(requests, "get", lambda url, timeout, headers: FakeResponse(status_code=404))

    result, author_ids = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)

    assert result[target] == {"status": "unavailable", "reason": "not_found"}
    assert target not in author_ids


def test_resolve_context_sensitive_media_match_is_filtered(monkeypatch):
    target = "mastodon.example/42"
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, timeout, headers: FakeResponse(
            {**status_payload(sensitive=True, spoiler_text=""), "media_attachments": [{"type": "image"}]}
        ),
    )

    result, _ = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)

    assert result[target] == {"status": "unavailable", "reason": "filtered"}


def test_resolve_context_non_discoverable_target_is_filtered(monkeypatch):
    target = "mastodon.example/42"
    monkeypatch.setattr(
        requests, "get", lambda url, timeout, headers: FakeResponse(status_payload(discoverable=False))
    )

    result, _ = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)

    assert result[target] == {"status": "unavailable", "reason": "filtered"}


def test_resolve_context_non_indexable_target_is_filtered(monkeypatch):
    target = "mastodon.example/42"
    monkeypatch.setattr(
        requests, "get", lambda url, timeout, headers: FakeResponse(status_payload(indexable=False))
    )

    result, _ = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)

    assert result[target] == {"status": "unavailable", "reason": "filtered"}


def test_resolve_context_noindex_target_is_filtered(monkeypatch):
    target = "mastodon.example/42"
    monkeypatch.setattr(requests, "get", lambda url, timeout, headers: FakeResponse(status_payload(noindex=True)))

    result, _ = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)

    assert result[target] == {"status": "unavailable", "reason": "filtered"}


def test_resolve_context_bot_target_is_filtered(monkeypatch):
    target = "mastodon.example/42"
    monkeypatch.setattr(requests, "get", lambda url, timeout, headers: FakeResponse(status_payload(bot=True)))

    result, _ = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)

    assert result[target] == {"status": "unavailable", "reason": "filtered"}


def test_resolve_context_null_discoverability_fields_default_to_opted_in(monkeypatch):
    target = "mastodon.example/42"
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, timeout, headers: FakeResponse(
            status_payload(discoverable=None, indexable=None, noindex=None)
        ),
    )

    result, _ = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)

    assert result[target]["status"] == "available"


def test_resolve_context_suppressed_domain_link_is_filtered(monkeypatch):
    target = "mastodon.example/42"
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, timeout, headers: FakeResponse(
            status_payload(content="<p>check this out https://amazon.com/dp/B00123</p>")
        ),
    )

    result, _ = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)

    assert result[target] == {"status": "unavailable", "reason": "filtered"}


def test_resolve_context_network_failure_omits_target_entirely(monkeypatch):
    target = "mastodon.example/42"

    def raise_error(*a, **k):
        raise requests.ConnectionError("network unreachable")

    monkeypatch.setattr(requests, "get", raise_error)

    result, author_ids = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)  # must not raise

    assert target not in result
    assert target not in author_ids


def test_resolve_context_http_error_status_omits_target_entirely(monkeypatch):
    target = "mastodon.example/42"
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, timeout, headers: FakeResponse(status_error=requests.HTTPError("500 server error")),
    )

    result, _ = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)  # must not raise

    assert target not in result


def test_resolve_context_dispatches_one_request_per_instance(monkeypatch):
    targets = ["instance-a.example/1", "instance-b.example/2"]
    calls = []

    def fake_get(url, timeout, headers):
        calls.append(url)
        return FakeResponse(status_payload())

    monkeypatch.setattr(requests, "get", fake_get)

    result, _ = mastodon_resolver.resolve_context(targets, TERMS, DOMAINS)

    assert calls == [
        "https://instance-a.example/api/v1/statuses/1",
        "https://instance-b.example/api/v1/statuses/2",
    ]
    assert all(result[t]["status"] == "available" for t in targets)


def test_resolve_context_dedupes_repeated_targets(monkeypatch):
    target = "mastodon.example/42"
    calls = []

    def fake_get(url, timeout, headers):
        calls.append(url)
        return FakeResponse(status_payload())

    monkeypatch.setattr(requests, "get", fake_get)

    mastodon_resolver.resolve_context([target, target, target], TERMS, DOMAINS)

    assert len(calls) == 1


def test_resolve_context_empty_input_makes_no_requests(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(1))

    result, author_ids = mastodon_resolver.resolve_context([], TERMS, DOMAINS)

    assert result == {}
    assert author_ids == {}
    assert calls == []


def test_resolve_context_malformed_target_is_skipped(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(1))

    result, author_ids = mastodon_resolver.resolve_context(["no-slash-here"], TERMS, DOMAINS)

    assert result == {}
    assert author_ids == {}
    assert calls == []


def test_resolve_context_non_dict_payload_is_not_found(monkeypatch):
    target = "mastodon.example/42"
    monkeypatch.setattr(requests, "get", lambda url, timeout, headers: FakeResponse([1, 2, 3]))

    result, _ = mastodon_resolver.resolve_context([target], TERMS, DOMAINS)

    assert result[target] == {"status": "unavailable", "reason": "not_found"}
