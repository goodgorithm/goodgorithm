import logging
from typing import Literal

import requests

from pipeline_stages import content_filter
from util.bluesky_appview import APPVIEW_BASE, APPVIEW_REQUEST_TIMEOUT_SECONDS, GET_POSTS_MAX_URIS

logger = logging.getLogger("processing")

ContextKind = Literal["quote", "reply"]


def extract_quote_uri(raw_json: dict) -> str | None:
    """Pulls the quoted post's AT-URI out of a Bluesky commit's embed, if
    any -- mirrors api/src/attachments.ts's embed-nesting exactly (direct
    quote: embed.record.uri; recordWithMedia: one level deeper at
    embed.record.record.uri). Only returns URIs that point at an actual
    post, not a list/starter-pack/feed-generator quote. See the wiki's
    Bluesky AppView Resolvers page."""
    record = (raw_json or {}).get("commit", {}).get("record", {})
    if not isinstance(record, dict):
        return None
    embed = record.get("embed")
    if not isinstance(embed, dict):
        return None

    embed_type = embed.get("$type")
    if embed_type == "app.bsky.embed.record":
        quote_record = embed.get("record")
    elif embed_type == "app.bsky.embed.recordWithMedia":
        wrapper = embed.get("record")
        quote_record = wrapper.get("record") if isinstance(wrapper, dict) else None
    else:
        return None

    if not isinstance(quote_record, dict):
        return None
    uri = quote_record.get("uri")
    if not isinstance(uri, str) or "/app.bsky.feed.post/" not in uri:
        return None
    return uri


def extract_reply_root_uri(raw_json: dict) -> str | None:
    """Pulls the thread root's AT-URI out of a Bluesky commit's reply
    record, if any -- record.reply.root, not .parent. root is required
    alongside parent on every reply record per the lexicon, client-
    declared same as parent -- we already trust a client's own embed/
    reply references everywhere else in context resolution (the quote
    embed's own URI, for instance), so trusting root costs nothing extra:
    still one AppView call, just a different URI. No chain-walking
    needed -- Bluesky already tells us the root directly."""
    record = (raw_json or {}).get("commit", {}).get("record", {})
    reply = record.get("reply") if isinstance(record, dict) else None
    root = reply.get("root") if isinstance(reply, dict) else None
    root_uri = root.get("uri") if isinstance(root, dict) else None
    return root_uri if isinstance(root_uri, str) else None


def extract_context_target(raw_json: dict) -> tuple[ContextKind, str] | None:
    """A post's single context-dependent target, if it has one -- a
    quote-embed takes priority over a reply-thread-root on the rare post
    that's both, since resolving a second context item per post is out
    of scope."""
    quote_uri = extract_quote_uri(raw_json)
    if quote_uri is not None:
        return "quote", quote_uri
    reply_uri = extract_reply_root_uri(raw_json)
    if reply_uri is not None:
        return "reply", reply_uri
    return None


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _at_uri_to_bsky_url(uri: str) -> str | None:
    """at://{did}/app.bsky.feed.post/{rkey} -> a bsky.app permalink, using
    the resolved postView's own uri -- always a DID, never whatever
    identifier form (DID or handle) the referencing post originally typed.
    Consumed by api/'s Mastodon quote-inline/RE: display path (context.py's
    only api/-facing source of a URL for that cross-platform case); inert
    for Bluesky-native display, which builds its own permalink directly
    from the referencing post's own raw_json instead."""
    parts = uri.split("/")
    if len(parts) != 5 or parts[3] != "app.bsky.feed.post":
        return None
    return f"https://bsky.app/profile/{parts[2]}/post/{parts[4]}"


def _map_post_view(post_view: dict, suppressed_terms: frozenset[str], suppressed_domains: frozenset[str]) -> dict:
    """Maps a hydrated postView into the exact display shape api/ serves
    verbatim. Never reads likeCount/repostCount/replyCount/quoteCount/
    bookmarkCount even though they're required/standard fields on
    postView -- deliberate, not an oversight. See CLAUDE.md's Post
    attachments & embeds section."""
    author = post_view.get("author")
    record = post_view.get("record")
    text = record.get("text") if isinstance(record, dict) else None
    if not isinstance(author, dict) or not isinstance(text, str):
        return {"status": "unavailable", "reason": "not_found"}

    # Same checks a regular post gets before it's ever stored, applied
    # here to the quoted post's own text/self-labels -- a quoted post
    # carries its own moderation status independent of the outer post
    # quoting it.
    if content_filter.is_content_excluded(
        "bluesky", text, {"commit": {"record": record}}, suppressed_terms, suppressed_domains
    ):
        return {"status": "unavailable", "reason": "filtered"}

    # postView.labels are moderation labels applied by labelers (e.g.
    # mod.bsky.app) as of resolution time -- the equivalent of the
    # labeler-stream backstop (blueskyLabels.ts), but for free here since
    # getPosts already returns current label state, no separate
    # subscription needed for quoted content. postView.author.labels
    # (also free in this same response) covers the target author's own
    # profile self-label -- a target author opted out of unauthenticated
    # viewing, self-declared as a bot, or carrying a labeler-applied
    # !hide/!warn all mean this content shouldn't be shown as resolved
    # context, same as a filtered post itself.
    author_labels = author.get("labels")
    if (
        content_filter.has_excluded_bluesky_labels(post_view.get("labels"), author_labels)
        or content_filter.has_no_unauthenticated_label(author_labels)
        or content_filter.has_bot_self_label(author_labels)
    ):
        return {"status": "unavailable", "reason": "filtered"}

    display_name = author.get("displayName")
    handle = author.get("handle")
    avatar = author.get("avatar")
    created_at = record.get("createdAt")
    uri = post_view.get("uri")

    return {
        "status": "available",
        "author": {
            "displayName": display_name if isinstance(display_name, str) else None,
            "handle": handle if isinstance(handle, str) else None,
            "avatarUrl": avatar if isinstance(avatar, str) else None,
        },
        "text": text,
        "createdAt": created_at if isinstance(created_at, str) else None,
        "url": _at_uri_to_bsky_url(uri) if isinstance(uri, str) else None,
    }


def resolve_context(
    uris: list[str], suppressed_terms: frozenset[str], suppressed_domains: frozenset[str]
) -> tuple[dict[str, dict], dict[str, str]]:
    """Batches into groups of GET_POSTS_MAX_URIS, calls Bluesky's public
    getPosts endpoint. Resolves a quote target and a reply-thread-root
    target identically -- both are just a Bluesky post URI to Bluesky's
    AppView, which doesn't care why the caller wanted it. Never crashes the
    calling cycle -- a failed batch just omits those URIs from the
    returned dicts entirely; a URI absent from a *successful* response
    maps to an explicit not_found status instead. See CLAUDE.md's Post
    attachments & embeds section for why (no retry, not_found vs. null
    semantics) and the wiki's Pipeline Internals page for the batching/
    failure-isolation mechanics.

    Returns (content_by_uri, author_did_by_uri) -- the second dict is a
    side channel for the caller's own author-identity lookups (e.g. an
    is_bot verdict check), populated only for "available" results; it's
    deliberately not part of the display shape in the first dict."""
    results: dict[str, dict] = {}
    author_dids: dict[str, str] = {}
    unique_uris = list(dict.fromkeys(uris))  # de-dupe, preserve order

    for batch in _chunk(unique_uris, GET_POSTS_MAX_URIS):
        try:
            response = requests.get(
                f"{APPVIEW_BASE}/app.bsky.feed.getPosts",
                params=[("uris", uri) for uri in batch],
                timeout=APPVIEW_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as err:
            logger.warning("context resolution failed for a batch of %d URIs: %s", len(batch), err)
            continue

        found_uris: set[str] = set()
        for post_view in payload.get("posts", []) if isinstance(payload, dict) else []:
            if not isinstance(post_view, dict):
                continue
            uri = post_view.get("uri")
            if not isinstance(uri, str):
                continue
            found_uris.add(uri)
            results[uri] = _map_post_view(post_view, suppressed_terms, suppressed_domains)
            author = post_view.get("author")
            did = author.get("did") if isinstance(author, dict) else None
            if isinstance(did, str):
                author_dids[uri] = did

        for uri in batch:
            if uri not in found_uris:
                results[uri] = {"status": "unavailable", "reason": "not_found"}

    return results, author_dids
