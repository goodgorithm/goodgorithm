import content_filter


def test_has_excluded_hashtag_matches_case_insensitively():
    assert content_filter.has_excluded_hashtag("great news #NSFW today") is True
    assert content_filter.has_excluded_hashtag("#nsfw book out now") is True


def test_has_excluded_hashtag_does_not_match_unlisted_tags():
    # #lesbian/#spanking deliberately excluded from EXCLUDED_HASHTAGS --
    # identity term / ambiguous-outside-context, see module docstring.
    assert content_filter.has_excluded_hashtag("#lesbian #spanking book out now") is False
    assert content_filter.has_excluded_hashtag("just a normal positive post") is False


def test_extract_self_label_values_reads_bluesky_self_labels():
    raw_json = {
        "commit": {
            "record": {
                "labels": {
                    "$type": "com.atproto.label.defs#selfLabels",
                    "values": [{"val": "porn"}, {"val": "some-other-value"}],
                }
            }
        }
    }
    assert content_filter.extract_self_label_values(raw_json) == ["porn", "some-other-value"]


def test_extract_self_label_values_returns_empty_for_mastodon_rows():
    # Mastodon raw_json has no "commit" key at all.
    raw_json = {"id": "12345", "sensitive": False, "content": "<p>hello</p>"}
    assert content_filter.extract_self_label_values(raw_json) == []


def test_extract_self_label_values_is_defensive_about_malformed_shapes():
    assert content_filter.extract_self_label_values({}) == []
    assert content_filter.extract_self_label_values({"commit": {}}) == []
    assert content_filter.extract_self_label_values({"commit": {"record": {"labels": None}}}) == []
    assert content_filter.extract_self_label_values({"commit": {"record": {"labels": {"values": "not-a-list"}}}}) == []


def test_has_excluded_self_label():
    excluded = {"commit": {"record": {"labels": {"values": [{"val": "sexual"}]}}}}
    clean = {"commit": {"record": {"labels": {"values": [{"val": "some-other-value"}]}}}}
    no_labels = {"commit": {"record": {}}}
    assert content_filter.has_excluded_self_label(excluded) is True
    assert content_filter.has_excluded_self_label(clean) is False
    assert content_filter.has_excluded_self_label(no_labels) is False


def test_is_content_excluded_combines_both_checks():
    hashtag_only = ("free book #nsfw", {"commit": {"record": {}}})
    label_only = ("a totally normal post", {"commit": {"record": {"labels": {"values": [{"val": "nudity"}]}}}})
    neither = ("a totally normal post", {"commit": {"record": {}}})

    assert content_filter.is_content_excluded(*hashtag_only) is True
    assert content_filter.is_content_excluded(*label_only) is True
    assert content_filter.is_content_excluded(*neither) is False
