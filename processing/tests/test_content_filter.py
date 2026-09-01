from pipeline_stages import content_filter

TERMS = frozenset({"nsfw"})
DOMAINS = frozenset({"amazon.com", "etsy.com"})
INSTANCE_DOMAINS = frozenset({"mastodon-sex.com"})


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


def test_has_excluded_home_instance_matches_remote_account_on_a_listed_instance():
    # issue #72: an account federated in from a fully dedicated adult
    # instance -- distinct from has_excluded_domain, which only looks at a
    # link inside the post itself, not the poster's own server.
    raw_json = {"account": {"acct": "someuser@mastodon-sex.com"}}
    assert content_filter.has_excluded_home_instance(raw_json, INSTANCE_DOMAINS) is True


def test_has_excluded_home_instance_matches_subdomain():
    raw_json = {"account": {"acct": "someuser@sub.mastodon-sex.com"}}
    assert content_filter.has_excluded_home_instance(raw_json, INSTANCE_DOMAINS) is True


def test_has_excluded_home_instance_does_not_match_local_account():
    # A local account's acct has no "@host" suffix -- nothing to check, and
    # none of our own polled instances are on the suppressed list anyway.
    raw_json = {"account": {"acct": "someuser"}}
    assert content_filter.has_excluded_home_instance(raw_json, INSTANCE_DOMAINS) is False


def test_has_excluded_home_instance_does_not_match_unlisted_instance():
    raw_json = {"account": {"acct": "someuser@mastodon.social"}}
    assert content_filter.has_excluded_home_instance(raw_json, INSTANCE_DOMAINS) is False


def test_has_excluded_home_instance_returns_false_for_bluesky_rows():
    # Bluesky raw_json has no "account" key in this shape at all.
    assert content_filter.has_excluded_home_instance({"commit": {"record": {}}}, INSTANCE_DOMAINS) is False


def test_has_excluded_home_instance_is_defensive_about_malformed_shapes():
    assert content_filter.has_excluded_home_instance({}, INSTANCE_DOMAINS) is False
    assert content_filter.has_excluded_home_instance(None, INSTANCE_DOMAINS) is False
    assert content_filter.has_excluded_home_instance({"account": "not-a-dict"}, INSTANCE_DOMAINS) is False
    assert content_filter.has_excluded_home_instance({"account": {"acct": None}}, INSTANCE_DOMAINS) is False


_FUNNEL = (
    "not posting it twice, check my bio instead 🤫 "
    "#egirl #curvymodel #inkedbabe #gothgirl #altstyle #bikini"
)


def test_has_bluesky_funnel_shape_matches_cta_plus_adult_tag_bag():
    assert content_filter.has_bluesky_funnel_shape("bluesky", _FUNNEL, frozenset()) is True


def test_has_bluesky_funnel_shape_requires_both_halves():
    cta_only = "peek at my bio if you want the real thing 🔥 #art #photography #portrait #print #gallery #forsale"
    tags_only = "new print drop today #egirl #curvymodel #inkedbabe #gothgirl #altstyle #bikini"
    assert content_filter.has_bluesky_funnel_shape("bluesky", cta_only, frozenset()) is False
    assert content_filter.has_bluesky_funnel_shape("bluesky", tags_only, frozenset()) is False


def test_has_bluesky_funnel_shape_is_bluesky_only():
    assert content_filter.has_bluesky_funnel_shape("mastodon", _FUNNEL, frozenset()) is False


def test_has_bluesky_funnel_shape_counts_live_suppressed_terms_toward_the_bag():
    # 3 base-vocab tags + 2 tags a moderator has just added to
    # suppressed_terms -> reaches the default threshold of 5.
    text = "link in bio 💌 #egirl #curvymodel #inkedbabe #rotato1 #rotato2"
    assert content_filter.has_bluesky_funnel_shape("bluesky", text, frozenset()) is False
    assert content_filter.has_bluesky_funnel_shape(
        "bluesky", text, frozenset({"rotato1", "rotato2"})
    ) is True


def test_has_bluesky_funnel_shape_does_not_match_legit_link_in_bio():
    # Real "link in bio" content that must survive: a CTA phrase without
    # the adult tag bag.
    musician = "new single out now, link in bio 🎸 #newmusic #indieband #vinyl #tour #synthpop #livemusic"
    comic = "page 42 is up! link in bio for the full archive #webcomic #comics #art #inktober #indiecomics #ink"
    mh = "you are not alone -- free confidential support, link in bio #mentalhealth #therapy #crisisline #support"
    for t in (musician, comic, mh):
        assert content_filter.has_bluesky_funnel_shape("bluesky", t, frozenset()) is False


def test_is_content_excluded_combines_all_seven_checks():
    combined_domains = DOMAINS | INSTANCE_DOMAINS
    hashtag_only = ("mastodon", "free book #nsfw", {"commit": {"record": {}}})
    bluesky_funnel_only = ("bluesky", _FUNNEL, {"commit": {"record": {}}})
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
    home_instance_only = (
        "mastodon",
        "a totally normal post",
        {"account": {"acct": "someuser@mastodon-sex.com"}},
    )
    neither = ("mastodon", "a totally normal post", {"commit": {"record": {}}})

    assert content_filter.is_content_excluded(*hashtag_only, TERMS, combined_domains) is True
    assert content_filter.is_content_excluded(*bluesky_funnel_only, TERMS, combined_domains) is True
    assert content_filter.is_content_excluded(*label_only, TERMS, combined_domains) is True
    assert content_filter.is_content_excluded(*spoiler_only, TERMS, combined_domains) is True
    assert content_filter.is_content_excluded(*domain_only, TERMS, combined_domains) is True
    assert content_filter.is_content_excluded(*sensitive_media_only, TERMS, combined_domains) is True
    assert content_filter.is_content_excluded(*home_instance_only, TERMS, combined_domains) is True
    assert content_filter.is_content_excluded(*neither, TERMS, combined_domains) is False
