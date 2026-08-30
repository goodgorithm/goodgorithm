from pipeline_stages import aggregator_demote

FLIPBOARD = frozenset({"flipboard.com", "flipboard.social"})


def test_federated_flipboard_account_is_demoted():
    # Mastodon author_id is "{polled_instance}/{acct}"; a federated account's
    # acct already carries its real "@home" -- see bot_filter.canonical_account_id.
    result = aggregator_demote.classify("mastodon", "hachyderm.io/TimesofIndia_@flipboard.com", FLIPBOARD)
    assert result.is_aggregator is True
    assert 0.0 < result.devalue_multiplier < 1.0
    assert result.devalue_multiplier == aggregator_demote.AGGREGATOR_DEMOTE_MULTIPLIER


def test_bare_acct_local_case_is_demoted():
    # If the polled instance IS the account's home, acct is a bare "user";
    # canonical_account_id reconstructs "user@{polled_instance}".
    result = aggregator_demote.classify("mastodon", "flipboard.com/somemagazine", FLIPBOARD)
    assert result.is_aggregator is True


def test_subdomain_of_listed_instance_is_demoted():
    result = aggregator_demote.classify("mastodon", "mstdn.social/feed@feeds.flipboard.com", FLIPBOARD)
    assert result.is_aggregator is True


def test_unlisted_instance_is_untouched():
    result = aggregator_demote.classify("mastodon", "fosstodon.org/realperson", FLIPBOARD)
    assert result.is_aggregator is False
    assert result.devalue_multiplier == 1.0


def test_bluesky_post_is_untouched():
    # Bluesky author_id is a bare DID -- no per-instance federation, nothing to match.
    result = aggregator_demote.classify("bluesky", "did:plc:flipboardcom", FLIPBOARD)
    assert result.is_aggregator is False
    assert result.devalue_multiplier == 1.0


def test_empty_list_is_untouched():
    result = aggregator_demote.classify("mastodon", "hachyderm.io/x@flipboard.com", frozenset())
    assert result.is_aggregator is False


def test_substring_but_not_suffix_instance_is_untouched():
    # "notflipboard.com" contains "flipboard.com" but isn't it or a subdomain of it.
    result = aggregator_demote.classify("mastodon", "mas.to/x@notflipboard.com", FLIPBOARD)
    assert result.is_aggregator is False
