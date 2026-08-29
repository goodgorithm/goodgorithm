from pipeline_stages import link_share


def bluesky_external(title: str | None) -> dict:
    external: dict = {"uri": "https://example.com/article"}
    if title is not None:
        external["title"] = title
    return {
        "commit": {
            "operation": "create",
            "collection": "app.bsky.feed.post",
            "record": {
                "$type": "app.bsky.feed.post",
                "text": "whatever",
                "embed": {"$type": "app.bsky.embed.external", "external": external},
            },
        }
    }


def bluesky_image() -> dict:
    return {
        "commit": {
            "record": {
                "$type": "app.bsky.feed.post",
                "text": "whatever",
                "embed": {"$type": "app.bsky.embed.images", "images": [{"alt": "a cat"}]},
            }
        }
    }


def mastodon_card(title: str | None) -> dict:
    card = {"url": "https://example.com/article", "type": "link"}
    if title is not None:
        card["title"] = title
    return {"id": "1", "card": card}


def test_bluesky_text_equals_title_is_devalued():
    raw = bluesky_external("Beef Stir Fry Recipe")
    result = link_share.classify("bluesky", raw, "Beef Stir Fry Recipe")
    assert result.is_bare_link_share is True
    assert 0.0 < result.devalue_multiplier < 1.0
    assert result.devalue_multiplier == link_share.LINK_SHARE_DEVALUE_MULTIPLIER


def test_bluesky_text_is_substring_of_titled_card_is_devalued():
    # Card titles routinely carry a " | Site Name" suffix the post text omits.
    raw = bluesky_external("Russia's Arctic Route | naked capitalism")
    result = link_share.classify("bluesky", raw, "Russia's Arctic Route https://example.com/article #news")
    assert result.is_bare_link_share is True


def test_bluesky_original_commentary_not_in_title_is_untouched():
    raw = bluesky_external("Fairphone 6+ is now official and coming to the US")
    text = "This is genuinely huge for the right-to-repair movement and I can't wait to try one."
    result = link_share.classify("bluesky", raw, text)
    assert result.is_bare_link_share is False
    assert result.devalue_multiplier == 1.0


def test_bluesky_empty_text_with_card_is_devalued():
    raw = bluesky_external("Some Article Title")
    result = link_share.classify("bluesky", raw, "https://example.com/article #blog")
    assert result.is_bare_link_share is True


def test_bluesky_image_embed_has_no_title_is_untouched():
    result = link_share.classify("bluesky", bluesky_image(), "Beef Stir Fry Recipe")
    assert result.is_bare_link_share is False


def test_bluesky_external_embed_without_title_is_untouched():
    result = link_share.classify("bluesky", bluesky_external(None), "Beef Stir Fry Recipe")
    assert result.is_bare_link_share is False


def test_mastodon_text_equals_card_title_is_devalued():
    raw = mastodon_card("9to5Mac Daily: August 28")
    result = link_share.classify("mastodon", raw, "9to5Mac Daily: August 28")
    assert result.is_bare_link_share is True


def test_mastodon_url_and_hashtags_only_is_devalued():
    raw = mastodon_card("Django Developers Survey 2026 results")
    result = link_share.classify("mastodon", raw, "https://example.com/article #django #python")
    assert result.is_bare_link_share is True


def test_mastodon_no_card_is_untouched():
    result = link_share.classify("mastodon", {"id": "1"}, "Just a regular post with no link at all")
    assert result.is_bare_link_share is False


def test_mastodon_genuine_commentary_is_untouched():
    raw = mastodon_card("Chicken as a Pizza topping, yay or nay?")
    result = link_share.classify(
        "mastodon", raw, "Hard nay from me, but the article makes a surprisingly good case for it."
    )
    assert result.is_bare_link_share is False


def test_long_text_over_char_cap_even_if_substring_is_untouched():
    padding = "context " * 40  # > LINK_SHARE_MAX_ORIGINAL_CHARS once stripped
    title = padding + "and a headline"
    raw = mastodon_card(title)
    result = link_share.classify("mastodon", raw, padding + "and a headline")
    assert len(padding) > link_share.LINK_SHARE_MAX_ORIGINAL_CHARS
    assert result.is_bare_link_share is False


def test_unknown_source_is_untouched():
    result = link_share.classify("rss", {"card": {"title": "x"}}, "x")
    assert result.is_bare_link_share is False
