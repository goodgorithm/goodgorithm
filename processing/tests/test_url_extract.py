from util.url_extract import extract_all_urls, extract_raw_url


def test_extract_raw_url_prefers_bluesky_embed_over_text():
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
    text = "check out https://other.example.com/decoy"
    assert extract_raw_url("bluesky", raw_json, text) == "https://example.com/article"


def test_extract_raw_url_prefers_mastodon_card_over_text():
    raw_json = {"card": {"url": "https://example.com/article"}}
    text = "check out https://other.example.com/decoy"
    assert extract_raw_url("mastodon", raw_json, text) == "https://example.com/article"


def test_extract_raw_url_falls_back_to_text_when_no_structured_embed():
    text = "check this out https://example.com/story #cool"
    assert extract_raw_url("mastodon", {}, text) == "https://example.com/story"
    assert extract_raw_url("bluesky", {"commit": {"record": {}}}, text) == "https://example.com/story"


def test_extract_raw_url_returns_none_when_no_url_present():
    assert extract_raw_url("mastodon", {}, "just a normal post") is None


def test_extract_raw_url_is_defensive_about_malformed_shapes():
    assert extract_raw_url("bluesky", None, "no url here") is None
    assert extract_raw_url("mastodon", {"card": "not-a-dict"}, "no url here") is None


def test_extract_all_urls_includes_embed_and_text_urls_bluesky():
    raw_json = {
        "commit": {
            "record": {
                "embed": {
                    "$type": "app.bsky.embed.external",
                    "external": {"uri": "https://esahubble.org/images/heic0408a/"},
                }
            }
        }
    }
    text = "Amazing telescope to start exploring the universe - https://amzn.to/4qE3k53 #TelescopeAdvisor"
    assert extract_all_urls("bluesky", raw_json, text) == [
        "https://esahubble.org/images/heic0408a/",
        "https://amzn.to/4qE3k53",
    ]


def test_extract_all_urls_includes_card_and_text_urls_mastodon():
    raw_json = {"card": {"url": "https://example.com/article"}}
    text = "also see https://other.example.com/second"
    assert extract_all_urls("mastodon", raw_json, text) == [
        "https://example.com/article",
        "https://other.example.com/second",
    ]


def test_extract_all_urls_returns_every_text_url_when_no_structured_embed():
    text = "see https://one.example.com and also https://two.example.com"
    assert extract_all_urls("mastodon", {}, text) == [
        "https://one.example.com",
        "https://two.example.com",
    ]


def test_extract_all_urls_dedupes_when_embed_url_repeated_in_text():
    raw_json = {"card": {"url": "https://example.com/article"}}
    text = "full story here: https://example.com/article"
    assert extract_all_urls("mastodon", raw_json, text) == ["https://example.com/article"]


def test_extract_all_urls_dedupes_repeated_text_urls():
    text = "https://example.com/x and again https://example.com/x"
    assert extract_all_urls("mastodon", {}, text) == ["https://example.com/x"]


def test_extract_all_urls_returns_empty_list_when_no_url_present():
    assert extract_all_urls("mastodon", {}, "just a normal post") == []


def test_extract_all_urls_is_defensive_about_malformed_shapes():
    assert extract_all_urls("bluesky", None, "no url here") == []
    assert extract_all_urls("mastodon", {"card": "not-a-dict"}, "no url here") == []
