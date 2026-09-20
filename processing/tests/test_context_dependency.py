from pipeline_stages import context_dependency

AUTHOR = "did:plc:author123"
OTHER = "did:plc:someoneelse"
TEXT = "hello"

MASTODON_AUTHOR_ID = "mastodon.example/someone"
MASTODON_INSTANCE = "mastodon.example"


def bluesky_raw(reply_parent_did: str | None = None, quote_uri: str | None = None) -> dict:
    record: dict = {"$type": "app.bsky.feed.post", "text": "hello"}
    if reply_parent_did is not None:
        record["reply"] = {
            "root": {"uri": f"at://{reply_parent_did}/app.bsky.feed.post/root123", "cid": "x"},
            "parent": {"uri": f"at://{reply_parent_did}/app.bsky.feed.post/parent123", "cid": "y"},
        }
    if quote_uri is not None:
        record["embed"] = {"$type": "app.bsky.embed.record", "record": {"cid": "z", "uri": quote_uri}}
    return {"did": AUTHOR, "commit": {"operation": "create", "collection": "app.bsky.feed.post", "record": record}}


def mastodon_raw(in_reply_to_id=None, content="just a regular post") -> dict:
    return {"id": "1", "in_reply_to_id": in_reply_to_id, "content": content}


def test_bluesky_non_reply_non_quote_is_none():
    result = context_dependency.classify("bluesky", AUTHOR, bluesky_raw(), TEXT)
    assert result.action == "none"
    assert result.context_kind is None
    assert result.context_target is None


def test_bluesky_reply_to_other_author_is_pending():
    result = context_dependency.classify("bluesky", AUTHOR, bluesky_raw(reply_parent_did=OTHER), TEXT)
    assert result.action == "pending"
    assert result.context_kind == "reply"
    assert result.context_target == f"at://{OTHER}/app.bsky.feed.post/parent123"


def test_bluesky_self_reply_thread_continuation_is_also_pending():
    # No same-author carve-out -- a reply is nonsensical without its
    # context regardless of who wrote the parent.
    result = context_dependency.classify("bluesky", AUTHOR, bluesky_raw(reply_parent_did=AUTHOR), TEXT)
    assert result.action == "pending"
    assert result.context_kind == "reply"


def test_bluesky_quote_is_pending():
    quote_uri = "at://did:plc:quoted/app.bsky.feed.post/q1"
    result = context_dependency.classify("bluesky", AUTHOR, bluesky_raw(quote_uri=quote_uri), TEXT)
    assert result.action == "pending"
    assert result.context_kind == "quote"
    assert result.context_target == quote_uri


def test_bluesky_quote_takes_priority_over_reply():
    quote_uri = "at://did:plc:quoted/app.bsky.feed.post/q1"
    result = context_dependency.classify(
        "bluesky", AUTHOR, bluesky_raw(reply_parent_did=OTHER, quote_uri=quote_uri), TEXT
    )
    assert result.context_kind == "quote"
    assert result.context_target == quote_uri


def test_bluesky_missing_reply_field_is_none():
    raw = {"did": AUTHOR, "commit": {"record": {"text": "hi"}}}
    assert context_dependency.classify("bluesky", AUTHOR, raw, TEXT).action == "none"


def test_bluesky_malformed_raw_json_does_not_raise():
    assert context_dependency.classify("bluesky", AUTHOR, {}, TEXT).action == "none"
    assert context_dependency.classify("bluesky", AUTHOR, None, TEXT).action == "none"


def test_mastodon_structured_reply_is_pending():
    result = context_dependency.classify("mastodon", MASTODON_AUTHOR_ID, mastodon_raw(in_reply_to_id="42"), TEXT)
    assert result.action == "pending"
    assert result.context_kind == "reply"
    assert result.context_target == f"{MASTODON_INSTANCE}/42"


def test_mastodon_quote_inline_is_pending():
    href = "https://bsky.app/profile/did:plc:quoted/post/q1"
    raw = mastodon_raw(content=f'RE: <a class="quote-inline" href="{href}">this post</a> great news')
    result = context_dependency.classify("mastodon", MASTODON_AUTHOR_ID, raw, TEXT)
    assert result.action == "pending"
    assert result.context_kind == "quote"
    assert result.context_target == "at://did:plc:quoted/app.bsky.feed.post/q1"


def test_mastodon_quote_inline_with_unparseable_href_is_excluded():
    raw = mastodon_raw(content='RE: <a class="quote-inline" href="not-a-bsky-url">this post</a> great news')
    result = context_dependency.classify("mastodon", MASTODON_AUTHOR_ID, raw, TEXT)
    assert result.action == "exclude"


def test_mastodon_ordinary_post_is_none():
    result = context_dependency.classify("mastodon", MASTODON_AUTHOR_ID, mastodon_raw(), TEXT)
    assert result.action == "none"


def test_unknown_platform_is_none():
    assert context_dependency.classify("unknown-platform", AUTHOR, {}, TEXT).action == "none"


# --- manually-typed "RE: <bsky.app post URL>", no quote-inline wrapper ---


def test_mastodon_manually_typed_bsky_re_reference_with_did_is_pending():
    text = "And the UK. RE: https://bsky.app/profile/did:plc:reu7q3altx5gsonhu5nxcfp6/post/3mseht2stlc2s"
    result = context_dependency.classify("mastodon", MASTODON_AUTHOR_ID, mastodon_raw(), text)
    assert result.action == "pending"
    assert result.context_kind == "quote"
    assert result.context_target == "at://did:plc:reu7q3altx5gsonhu5nxcfp6/app.bsky.feed.post/3mseht2stlc2s"


def test_mastodon_manually_typed_bsky_re_reference_with_handle_is_pending():
    text = (
        "crazy that wishbone is 1 year old already! great album, quite an "
        "experience listening to it all in one go! "
        "RE: https://bsky.app/profile/wbtourupdates.bsky.social/post/3mt3s7fifbg25"
    )
    result = context_dependency.classify("mastodon", MASTODON_AUTHOR_ID, mastodon_raw(), text)
    assert result.action == "pending"
    assert result.context_kind == "quote"
    assert result.context_target == "at://wbtourupdates.bsky.social/app.bsky.feed.post/3mt3s7fifbg25"


def test_mastodon_re_without_a_bsky_url_is_not_excluded():
    text = "RE: my earlier point, I think you're right"
    result = context_dependency.classify("mastodon", MASTODON_AUTHOR_ID, mastodon_raw(), text)
    assert result.action == "none"


def test_mastodon_bsky_url_without_re_prefix_is_not_excluded():
    text = "check this out https://bsky.app/profile/someone.bsky.social/post/abc123"
    result = context_dependency.classify("mastodon", MASTODON_AUTHOR_ID, mastodon_raw(), text)
    assert result.action == "none"


def test_mastodon_reply_takes_priority_over_quote_inline():
    href = "https://bsky.app/profile/did:plc:quoted/post/q1"
    raw = mastodon_raw(
        in_reply_to_id="42", content=f'RE: <a class="quote-inline" href="{href}">this post</a> great news'
    )
    result = context_dependency.classify("mastodon", MASTODON_AUTHOR_ID, raw, TEXT)
    assert result.context_kind == "reply"
    assert result.context_target == f"{MASTODON_INSTANCE}/42"


def test_mastodon_reply_with_no_polled_instance_in_author_id_is_none():
    result = context_dependency.classify("mastodon", "", mastodon_raw(in_reply_to_id="42"), TEXT)
    assert result.action == "none"
