from util.url_extract import extract_raw_url


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
