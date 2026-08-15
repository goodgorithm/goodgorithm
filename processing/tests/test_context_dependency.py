import context_dependency

AUTHOR = "did:plc:author123"
OTHER = "did:plc:someoneelse"
TEXT = "hello"


def bluesky_raw(reply_parent_did: str | None = None) -> dict:
    record: dict = {"$type": "app.bsky.feed.post", "text": "hello"}
    if reply_parent_did is not None:
        record["reply"] = {
            "root": {"uri": f"at://{reply_parent_did}/app.bsky.feed.post/root123", "cid": "x"},
            "parent": {"uri": f"at://{reply_parent_did}/app.bsky.feed.post/parent123", "cid": "y"},
        }
    return {"did": AUTHOR, "commit": {"operation": "create", "collection": "app.bsky.feed.post", "record": record}}


def mastodon_raw(in_reply_to_id=None, content="just a regular post") -> dict:
    return {"id": "1", "in_reply_to_id": in_reply_to_id, "content": content}


def test_bluesky_non_reply_is_none():
    result = context_dependency.classify("bluesky", AUTHOR, bluesky_raw(), TEXT)
    assert result.action == "none"
    assert result.devalue_multiplier == 1.0


def test_bluesky_reply_to_other_author_is_devalued():
    result = context_dependency.classify("bluesky", AUTHOR, bluesky_raw(reply_parent_did=OTHER), TEXT)
    assert result.action == "devalue"
    assert 0.0 < result.devalue_multiplier < 1.0


def test_bluesky_self_reply_thread_continuation_is_none():
    result = context_dependency.classify("bluesky", AUTHOR, bluesky_raw(reply_parent_did=AUTHOR), TEXT)
    assert result.action == "none"


def test_bluesky_missing_reply_field_is_none():
    raw = {"did": AUTHOR, "commit": {"record": {"text": "hi"}}}
    assert context_dependency.classify("bluesky", AUTHOR, raw, TEXT).action == "none"


def test_bluesky_malformed_raw_json_does_not_raise():
    assert context_dependency.classify("bluesky", AUTHOR, {}, TEXT).action == "none"
    assert context_dependency.classify("bluesky", AUTHOR, None, TEXT).action == "none"


def test_mastodon_structured_reply_is_excluded():
    result = context_dependency.classify("mastodon", "acct", mastodon_raw(in_reply_to_id="42"), TEXT)
    assert result.action == "exclude"


def test_mastodon_quote_inline_is_excluded():
    raw = mastodon_raw(content='RE: <a class="quote-inline" href="...">this post</a> great news')
    assert context_dependency.classify("mastodon", "acct", raw, TEXT).action == "exclude"


def test_mastodon_ordinary_post_is_none():
    result = context_dependency.classify("mastodon", "acct", mastodon_raw(), TEXT)
    assert result.action == "none"
    assert result.devalue_multiplier == 1.0


def test_unknown_platform_is_none():
    assert context_dependency.classify("unknown-platform", "x", {}, TEXT).action == "none"


# --- manually-typed "RE: <bsky.app post URL>" (issue #33 follow-up) ---
#
# Confirmed live in production: a Bridgy-Fed-bridged quote always carries
# the quote-inline class (already covered above), but a real Mastodon
# user can also just type "RE: <bsky.app post URL>" themselves, with no
# such wrapper at all -- confirmed via a real post from
# hachyderm.io/jack@j4ck.xyz. The text pattern is matched directly so
# both cases are caught, not just Bridgy Fed's specific implementation.


def test_mastodon_manually_typed_bsky_re_reference_with_did_is_excluded():
    text = "And the UK. RE: https://bsky.app/profile/did:plc:reu7q3altx5gsonhu5nxcfp6/post/3mseht2stlc2s"
    result = context_dependency.classify("mastodon", "acct", mastodon_raw(), text)
    assert result.action == "exclude"


def test_mastodon_manually_typed_bsky_re_reference_with_handle_is_excluded():
    # Real example: hachyderm.io/jack@j4ck.xyz, no quote-inline class at all.
    text = (
        "crazy that wishbone is 1 year old already! great album, quite an "
        "experience listening to it all in one go! "
        "RE: https://bsky.app/profile/wbtourupdates.bsky.social/post/3mt3s7fifbg25"
    )
    result = context_dependency.classify("mastodon", "acct", mastodon_raw(), text)
    assert result.action == "exclude"


def test_mastodon_re_without_a_bsky_url_is_not_excluded():
    text = "RE: my earlier point, I think you're right"
    result = context_dependency.classify("mastodon", "acct", mastodon_raw(), text)
    assert result.action == "none"


def test_mastodon_bsky_url_without_re_prefix_is_not_excluded():
    text = "check this out https://bsky.app/profile/someone.bsky.social/post/abc123"
    result = context_dependency.classify("mastodon", "acct", mastodon_raw(), text)
    assert result.action == "none"
