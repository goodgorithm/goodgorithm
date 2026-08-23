from pipeline_stages import content_filter

TERMS = frozenset({"nsfw"})
DOMAINS = frozenset({"amazon.com", "etsy.com"})


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


def test_has_excluded_domain_matches_exact_domain():
    raw_json = {"card": {"url": "https://amazon.com/dp/B00123"}}
    assert content_filter.has_excluded_domain("mastodon", raw_json, "check this out", DOMAINS) is True


def test_has_excluded_domain_matches_subdomain():
    raw_json = {"card": {"url": "https://www.amazon.com/dp/B00123"}}
    assert content_filter.has_excluded_domain("mastodon", raw_json, "check this out", DOMAINS) is True
    raw_json_smile = {"card": {"url": "https://smile.amazon.com/dp/B00123"}}
    assert content_filter.has_excluded_domain("mastodon", raw_json_smile, "check this out", DOMAINS) is True


def test_has_excluded_domain_matches_bare_domain_with_no_path():
    # Deliberately unlike dedup.py's extract_dedup_url, which rejects
    # bare-domain URLs -- a homepage-only marketplace link should still
    # match here.
    raw_json = {"card": {"url": "https://www.amazon.com"}}
    assert content_filter.has_excluded_domain("mastodon", raw_json, "check this out", DOMAINS) is True


def test_has_excluded_domain_does_not_match_unlisted_domain():
    raw_json = {"card": {"url": "https://example.com/some-article"}}
    assert content_filter.has_excluded_domain("mastodon", raw_json, "check this out", DOMAINS) is False


def test_has_excluded_domain_does_not_match_lookalike_domain():
    # "notamazon.com" ends with "amazon.com" as a raw string but isn't a
    # subdomain of it -- the "." + domain suffix check must reject this.
    raw_json = {"card": {"url": "https://notamazon.com/dp/B00123"}}
    assert content_filter.has_excluded_domain("mastodon", raw_json, "check this out", DOMAINS) is False


def test_has_excluded_domain_falls_back_to_text_url():
    text = "great find https://etsy.com/listing/12345 highly recommend"
    assert content_filter.has_excluded_domain("mastodon", {}, text, DOMAINS) is True


def test_has_excluded_domain_is_defensive_about_no_url():
    assert content_filter.has_excluded_domain("mastodon", {}, "just a normal post", DOMAINS) is False


def test_has_excluded_sensitive_media_matches_media_with_no_spoiler_text():
    # issue #72: the one sub-case a real production sample confirmed
    # high-precision for adult content.
    raw_json = {"sensitive": True, "spoiler_text": "", "media_attachments": [{"type": "image"}]}
    assert content_filter.has_excluded_sensitive_media(raw_json) is True


def test_has_excluded_sensitive_media_does_not_match_without_media():
    # No media -- confirmed by real sampling to be mostly ordinary
    # CW-culture text (spoilers, mental-health disclosure), not adult
    # content, even when sensitive=true.
    raw_json = {"sensitive": True, "spoiler_text": "", "media_attachments": []}
    assert content_filter.has_excluded_sensitive_media(raw_json) is False
    assert content_filter.has_excluded_sensitive_media({"sensitive": True, "spoiler_text": ""}) is False


def test_has_excluded_sensitive_media_does_not_match_with_spoiler_text():
    # Media + an actual spoiler_text turned out mixed in the real sample
    # (news/political images, courtesy "eye contact" selfie tags, artistic
    # content, alongside genuine adult posts) -- deliberately not included
    # in the hard-exclude scope, unlike the no-spoiler-text case above.
    raw_json = {"sensitive": True, "spoiler_text": "eye contact", "media_attachments": [{"type": "image"}]}
    assert content_filter.has_excluded_sensitive_media(raw_json) is False


def test_has_excluded_sensitive_media_does_not_match_when_not_flagged_sensitive():
    raw_json = {"sensitive": False, "spoiler_text": "", "media_attachments": [{"type": "image"}]}
    assert content_filter.has_excluded_sensitive_media(raw_json) is False


def test_has_excluded_sensitive_media_returns_false_for_bluesky_rows():
    # Bluesky raw_json has no top-level "sensitive"/"media_attachments"
    # keys at all -- its adult content is already hard-excluded via
    # has_excluded_self_label instead.
    assert content_filter.has_excluded_sensitive_media({"commit": {"record": {}}}) is False


def test_has_excluded_sensitive_media_is_defensive_about_malformed_shapes():
    assert content_filter.has_excluded_sensitive_media({}) is False
    assert content_filter.has_excluded_sensitive_media(None) is False
    assert content_filter.has_excluded_sensitive_media({"sensitive": True, "media_attachments": "not-a-list"}) is False


def test_is_content_excluded_combines_all_five_checks():
    hashtag_only = ("mastodon", "free book #nsfw", {"commit": {"record": {}}})
    label_only = (
        "bluesky",
        "a totally normal post",
        {"commit": {"record": {"labels": {"values": [{"val": "nudity"}]}}}},
    )
    spoiler_only = ("mastodon", "a totally normal post", {"spoiler_text": "nsfw"})
    domain_only = ("mastodon", "a totally normal post", {"card": {"url": "https://amazon.com/dp/B00123"}})
    sensitive_media_only = (
        "mastodon",
        "good morning everyone",
        {"sensitive": True, "spoiler_text": "", "media_attachments": [{"type": "image"}]},
    )
    neither = ("mastodon", "a totally normal post", {"commit": {"record": {}}})

    assert content_filter.is_content_excluded(*hashtag_only, TERMS, DOMAINS) is True
    assert content_filter.is_content_excluded(*label_only, TERMS, DOMAINS) is True
    assert content_filter.is_content_excluded(*spoiler_only, TERMS, DOMAINS) is True
    assert content_filter.is_content_excluded(*domain_only, TERMS, DOMAINS) is True
    assert content_filter.is_content_excluded(*sensitive_media_only, TERMS, DOMAINS) is True
    assert content_filter.is_content_excluded(*neither, TERMS, DOMAINS) is False
