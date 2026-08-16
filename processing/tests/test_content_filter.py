from pipeline_stages import content_filter

TERMS = frozenset({"nsfw"})


def test_has_excluded_hashtag_matches_case_insensitively():
    assert content_filter.has_excluded_hashtag("great news #NSFW today", TERMS) is True
    assert content_filter.has_excluded_hashtag("#nsfw book out now", TERMS) is True


def test_has_excluded_hashtag_does_not_match_unlisted_tags():
    # #lesbian/#spanking deliberately not in the suppressed-terms list --
    # identity term / ambiguous-outside-context, see the migration's
    # comment (0009_add_suppressed_terms.sql).
    assert content_filter.has_excluded_hashtag("#lesbian #spanking book out now", TERMS) is False
    assert content_filter.has_excluded_hashtag("just a normal positive post", TERMS) is False


def test_has_excluded_spoiler_text_matches_case_insensitively():
    assert content_filter.has_excluded_spoiler_text({"spoiler_text": "NSFW"}, TERMS) is True
    assert content_filter.has_excluded_spoiler_text({"spoiler_text": "cw: nsfw content"}, TERMS) is True


def test_has_excluded_spoiler_text_requires_a_whole_word_match():
    # "nsfwoosh" contains "nsfw" as a substring but isn't the term itself --
    # proves \b is doing real work, not a bare `in` check.
    assert content_filter.has_excluded_spoiler_text({"spoiler_text": "nsfwoosh nonsense"}, TERMS) is False


def test_has_excluded_spoiler_text_does_not_match_unrelated_content_warnings():
    assert content_filter.has_excluded_spoiler_text({"spoiler_text": "spoilers: series finale"}, TERMS) is False


def test_has_excluded_spoiler_text_is_defensive_about_missing_or_empty():
    assert content_filter.has_excluded_spoiler_text({}, TERMS) is False
    assert content_filter.has_excluded_spoiler_text({"spoiler_text": ""}, TERMS) is False
    assert content_filter.has_excluded_spoiler_text({"spoiler_text": None}, TERMS) is False
    # Bluesky raw_json has no spoiler_text key at all.
    assert content_filter.has_excluded_spoiler_text({"commit": {"record": {}}}, TERMS) is False


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


def test_is_content_excluded_combines_all_three_checks():
    hashtag_only = ("free book #nsfw", {"commit": {"record": {}}})
    label_only = ("a totally normal post", {"commit": {"record": {"labels": {"values": [{"val": "nudity"}]}}}})
    spoiler_only = ("a totally normal post", {"spoiler_text": "nsfw"})
    neither = ("a totally normal post", {"commit": {"record": {}}})

    assert content_filter.is_content_excluded(*hashtag_only, TERMS) is True
    assert content_filter.is_content_excluded(*label_only, TERMS) is True
    assert content_filter.is_content_excluded(*spoiler_only, TERMS) is True
    assert content_filter.is_content_excluded(*neither, TERMS) is False
