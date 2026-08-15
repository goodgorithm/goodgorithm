import context_dependency

AUTHOR = "did:plc:author123"
OTHER = "did:plc:someoneelse"


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
    result = context_dependency.classify("bluesky", AUTHOR, bluesky_raw())
    assert result.action == "none"
    assert result.devalue_multiplier == 1.0


def test_bluesky_reply_to_other_author_is_devalued():
    result = context_dependency.classify("bluesky", AUTHOR, bluesky_raw(reply_parent_did=OTHER))
    assert result.action == "devalue"
    assert 0.0 < result.devalue_multiplier < 1.0


def test_bluesky_self_reply_thread_continuation_is_none():
    result = context_dependency.classify("bluesky", AUTHOR, bluesky_raw(reply_parent_did=AUTHOR))
    assert result.action == "none"


def test_bluesky_missing_reply_field_is_none():
    raw = {"did": AUTHOR, "commit": {"record": {"text": "hi"}}}
    assert context_dependency.classify("bluesky", AUTHOR, raw).action == "none"


def test_bluesky_malformed_raw_json_does_not_raise():
    assert context_dependency.classify("bluesky", AUTHOR, {}).action == "none"
    assert context_dependency.classify("bluesky", AUTHOR, None).action == "none"


def test_mastodon_structured_reply_is_excluded():
    result = context_dependency.classify("mastodon", "acct", mastodon_raw(in_reply_to_id="42"))
    assert result.action == "exclude"


def test_mastodon_quote_inline_is_excluded():
    raw = mastodon_raw(content='RE: <a class="quote-inline" href="...">this post</a> great news')
    assert context_dependency.classify("mastodon", "acct", raw).action == "exclude"


def test_mastodon_ordinary_post_is_none():
    result = context_dependency.classify("mastodon", "acct", mastodon_raw())
    assert result.action == "none"
    assert result.devalue_multiplier == 1.0


def test_unknown_platform_is_none():
    assert context_dependency.classify("unknown-platform", "x", {}).action == "none"
