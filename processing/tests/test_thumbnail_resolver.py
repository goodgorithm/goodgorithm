import requests

import thumbnail_resolver

# --- _is_safe_public_url ---


def test_is_safe_public_url_accepts_a_real_public_ip():
    assert thumbnail_resolver._is_safe_public_url("https://8.8.8.8/") is True


def test_is_safe_public_url_rejects_loopback():
    assert thumbnail_resolver._is_safe_public_url("http://127.0.0.1/") is False
    assert thumbnail_resolver._is_safe_public_url("http://127.0.0.1:8080/admin") is False


def test_is_safe_public_url_rejects_cloud_metadata_endpoint():
    assert thumbnail_resolver._is_safe_public_url("http://169.254.169.254/latest/meta-data/") is False


def test_is_safe_public_url_rejects_private_ranges():
    assert thumbnail_resolver._is_safe_public_url("http://10.0.0.5/") is False
    assert thumbnail_resolver._is_safe_public_url("http://192.168.1.1/") is False
    assert thumbnail_resolver._is_safe_public_url("http://172.16.0.1/") is False


def test_is_safe_public_url_rejects_non_http_schemes():
    assert thumbnail_resolver._is_safe_public_url("file:///etc/passwd") is False
    assert thumbnail_resolver._is_safe_public_url("ftp://8.8.8.8/") is False


def test_is_safe_public_url_rejects_malformed_urls():
    assert thumbnail_resolver._is_safe_public_url("not a url") is False
    assert thumbnail_resolver._is_safe_public_url("") is False


# --- resolve_thumbnail ---


class FakeRaw:
    def __init__(self, body: bytes):
        self._body = body

    def read(self, size, decode_content=True):
        return self._body


class FakeResponse:
    def __init__(self, status_code=200, body=b"", headers=None, encoding="utf-8"):
        self.status_code = status_code
        self.headers = headers or {}
        self.encoding = encoding
        self.raw = FakeRaw(body)

    @property
    def is_redirect(self):
        return "Location" in self.headers and self.status_code in (301, 302, 303, 307, 308)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_resolve_thumbnail_extracts_og_image(monkeypatch):
    html = b'<html><head><meta property="og:image" content="https://example.com/thumb.jpg"></head></html>'
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(body=html))

    assert thumbnail_resolver.resolve_thumbnail("https://8.8.8.8/article") == "https://example.com/thumb.jpg"


def test_resolve_thumbnail_decodes_html_entities_in_the_url(monkeypatch):
    # Real production regression: openai.com's og:image content attribute
    # has a literal "&amp;" between query params - left undecoded, that
    # corrupts the URL's query string when actually fetched.
    html = b'<meta property="og:image" content="https://example.com/img.png?w=1600&amp;h=900">'
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(body=html))

    assert thumbnail_resolver.resolve_thumbnail("https://8.8.8.8/article") == "https://example.com/img.png?w=1600&h=900"


def test_resolve_thumbnail_handles_reversed_attribute_order(monkeypatch):
    html = b'<meta content="https://example.com/thumb.jpg" property="og:image">'
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(body=html))

    assert thumbnail_resolver.resolve_thumbnail("https://8.8.8.8/article") == "https://example.com/thumb.jpg"


def test_resolve_thumbnail_falls_back_to_twitter_image(monkeypatch):
    html = b'<meta name="twitter:image" content="https://example.com/tw-thumb.jpg">'
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(body=html))

    assert thumbnail_resolver.resolve_thumbnail("https://8.8.8.8/article") == "https://example.com/tw-thumb.jpg"


def test_resolve_thumbnail_prefers_og_image_over_twitter_image(monkeypatch):
    html = (
        b'<meta name="twitter:image" content="https://example.com/tw-thumb.jpg">'
        b'<meta property="og:image" content="https://example.com/og-thumb.jpg">'
    )
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(body=html))

    assert thumbnail_resolver.resolve_thumbnail("https://8.8.8.8/article") == "https://example.com/og-thumb.jpg"


def test_resolve_thumbnail_returns_none_when_no_matching_tag(monkeypatch):
    html = b"<html><head><title>No image here</title></head></html>"
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(body=html))

    assert thumbnail_resolver.resolve_thumbnail("https://8.8.8.8/article") is None


def test_resolve_thumbnail_returns_none_on_non_200(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(status_code=404))

    assert thumbnail_resolver.resolve_thumbnail("https://8.8.8.8/missing") is None


def test_resolve_thumbnail_returns_none_on_network_failure(monkeypatch):
    def raise_error(*a, **k):
        raise requests.ConnectionError("network unreachable")

    monkeypatch.setattr(requests, "get", raise_error)

    assert thumbnail_resolver.resolve_thumbnail("https://8.8.8.8/article") is None  # must not raise


def test_resolve_thumbnail_rejects_an_unsafe_starting_url(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(1))

    assert thumbnail_resolver.resolve_thumbnail("http://169.254.169.254/") is None
    assert calls == []  # never even attempted the request


def test_resolve_thumbnail_follows_a_safe_redirect(monkeypatch):
    html = b'<meta property="og:image" content="https://example.com/thumb.jpg">'
    responses = [
        FakeResponse(status_code=302, headers={"Location": "https://8.8.4.4/final"}),
        FakeResponse(body=html),
    ]
    monkeypatch.setattr(requests, "get", lambda *a, **k: responses.pop(0))

    assert thumbnail_resolver.resolve_thumbnail("https://8.8.8.8/redirect-me") == "https://example.com/thumb.jpg"


def test_resolve_thumbnail_does_not_follow_a_redirect_to_an_unsafe_address(monkeypatch):
    # A URL can pass the initial safety check and still redirect somewhere
    # unsafe -- each hop must be re-validated, not just the starting URL.
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return FakeResponse(status_code=302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})

    monkeypatch.setattr(requests, "get", fake_get)

    assert thumbnail_resolver.resolve_thumbnail("https://8.8.8.8/redirect-me") is None
    assert len(calls) == 1  # only the first (safe) hop was ever fetched


def test_resolve_thumbnail_gives_up_after_max_redirects(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return FakeResponse(status_code=302, headers={"Location": "https://8.8.4.4/next"})

    monkeypatch.setattr(requests, "get", fake_get)

    assert thumbnail_resolver.resolve_thumbnail("https://8.8.8.8/loop") is None
    assert len(calls) == thumbnail_resolver.MAX_REDIRECTS + 1


# --- resolve_thumbnails ---


def test_resolve_thumbnails_dedupes_repeated_urls(monkeypatch):
    calls = []
    html = b'<meta property="og:image" content="https://example.com/thumb.jpg">'

    def fake_get(url, **kwargs):
        calls.append(url)
        return FakeResponse(body=html)

    monkeypatch.setattr(requests, "get", fake_get)

    url = "https://8.8.8.8/article"
    result = thumbnail_resolver.resolve_thumbnails([url, url, url])

    assert len(calls) == 1
    assert result == {url: "https://example.com/thumb.jpg"}


def test_resolve_thumbnails_empty_input_makes_no_requests(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(1))

    assert thumbnail_resolver.resolve_thumbnails([]) == {}
    assert calls == []


# --- extract_link_needing_thumbnail ---


def test_extract_link_needing_thumbnail_bluesky_no_thumb():
    raw_json = {
        "commit": {
            "record": {
                "embed": {
                    "$type": "app.bsky.embed.external",
                    "external": {"uri": "https://example.com/article"},
                }
            }
        }
    }
    assert thumbnail_resolver.extract_link_needing_thumbnail("bluesky", raw_json) == "https://example.com/article"


def test_extract_link_needing_thumbnail_bluesky_already_has_thumb():
    raw_json = {
        "commit": {
            "record": {
                "embed": {
                    "$type": "app.bsky.embed.external",
                    "external": {
                        "uri": "https://example.com/article",
                        "thumb": {"ref": {"$link": "abc123"}},
                    },
                }
            }
        }
    }
    assert thumbnail_resolver.extract_link_needing_thumbnail("bluesky", raw_json) is None


def test_extract_link_needing_thumbnail_bluesky_non_external_embed():
    raw_json = {"commit": {"record": {"embed": {"$type": "app.bsky.embed.images", "images": []}}}}
    assert thumbnail_resolver.extract_link_needing_thumbnail("bluesky", raw_json) is None


def test_extract_link_needing_thumbnail_mastodon_no_image():
    raw_json = {"card": {"url": "https://example.com/article", "image": None}}
    assert thumbnail_resolver.extract_link_needing_thumbnail("mastodon", raw_json) == "https://example.com/article"


def test_extract_link_needing_thumbnail_mastodon_already_has_image():
    raw_json = {"card": {"url": "https://example.com/article", "image": "https://example.com/thumb.jpg"}}
    assert thumbnail_resolver.extract_link_needing_thumbnail("mastodon", raw_json) is None


def test_extract_link_needing_thumbnail_mastodon_no_card():
    assert thumbnail_resolver.extract_link_needing_thumbnail("mastodon", {"card": None}) is None


def test_extract_link_needing_thumbnail_is_defensive_about_malformed_shapes():
    assert thumbnail_resolver.extract_link_needing_thumbnail("bluesky", {}) is None
    assert thumbnail_resolver.extract_link_needing_thumbnail("bluesky", None) is None
    assert thumbnail_resolver.extract_link_needing_thumbnail("mastodon", {}) is None
    assert thumbnail_resolver.extract_link_needing_thumbnail("unknown-source", {"card": {"url": "x"}}) is None
