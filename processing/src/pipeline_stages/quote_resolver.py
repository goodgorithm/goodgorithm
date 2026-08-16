import logging
import os

import requests

from pipeline_stages import content_filter

logger = logging.getLogger("processing")

# Bluesky's own public, unauthenticated AppView instance -- not something
# an operator would tune, so it's not an env var, same as ingestion/'s
# Jetstream URL. See the wiki's Bluesky Protocol page.
APPVIEW_BASE = "https://public.api.bsky.app/xrpc"
# app.bsky.feed.getPosts' documented max URIs per call -- an external API
# limit, not a tunable; raising this would just make oversized batches
# fail against Bluesky's own enforcement.
GET_POSTS_MAX_URIS = 25
QUOTE_RESOLVER_REQUEST_TIMEOUT_SECONDS = int(os.environ.get("QUOTE_RESOLVER_REQUEST_TIMEOUT_SECONDS", "10"))


def extract_quote_uri(raw_json: dict) -> str | None:
    """Pulls the quoted post's AT-URI out of a Bluesky commit's embed, if
    any -- mirrors api/src/attachments.ts's embed-nesting exactly (direct
    quote: embed.record.uri; recordWithMedia: one level deeper at
    embed.record.record.uri). Only returns URIs that point at an actual
    post, not a list/starter-pack/feed-generator quote. See the wiki's
    Pipeline Internals page."""
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


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _map_post_view(post_view: dict, suppressed_terms: frozenset[str]) -> dict:
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
    if content_filter.is_content_excluded(text, {"commit": {"record": record}}, suppressed_terms):
        return {"status": "unavailable", "reason": "filtered"}

    # postView.labels are moderation labels applied by labelers (e.g.
    # mod.bsky.app) as of resolution time -- the equivalent of the
    # labeler-stream backstop (blueskyLabels.ts), but for free here since
    # getPosts already returns current label state, no separate
    # subscription needed for quoted content.
    labels = post_view.get("labels")
    if isinstance(labels, list):
        label_values = [v.get("val") for v in labels if isinstance(v, dict) and isinstance(v.get("val"), str)]
        if any(v in content_filter.ADULT_LABEL_VALUES for v in label_values):
            return {"status": "unavailable", "reason": "filtered"}

    display_name = author.get("displayName")
    handle = author.get("handle")
    avatar = author.get("avatar")
    created_at = record.get("createdAt")

    return {
        "status": "available",
        "author": {
            "displayName": display_name if isinstance(display_name, str) else None,
            "handle": handle if isinstance(handle, str) else None,
            "avatarUrl": avatar if isinstance(avatar, str) else None,
        },
        "text": text,
        "createdAt": created_at if isinstance(created_at, str) else None,
    }


def resolve_quotes(uris: list[str], suppressed_terms: frozenset[str]) -> dict[str, dict]:
    """Batches into groups of GET_POSTS_MAX_URIS, calls Bluesky's public
    getPosts endpoint. Never crashes the calling cycle -- a failed batch
    just omits those URIs from the returned dict entirely; a URI absent
    from a *successful* response maps to an explicit not_found status
    instead. See CLAUDE.md's Post attachments & embeds section for why
    (no retry, not_found vs. null semantics) and the wiki's Pipeline
    Internals page for the batching/failure-isolation mechanics."""
    results: dict[str, dict] = {}
    unique_uris = list(dict.fromkeys(uris))  # de-dupe, preserve order

    for batch in _chunk(unique_uris, GET_POSTS_MAX_URIS):
        try:
            response = requests.get(
                f"{APPVIEW_BASE}/app.bsky.feed.getPosts",
                params=[("uris", uri) for uri in batch],
                timeout=QUOTE_RESOLVER_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as err:
            logger.warning("quote resolution failed for a batch of %d URIs: %s", len(batch), err)
            continue

        found_uris: set[str] = set()
        for post_view in payload.get("posts", []) if isinstance(payload, dict) else []:
            if not isinstance(post_view, dict):
                continue
            uri = post_view.get("uri")
            if not isinstance(uri, str):
                continue
            found_uris.add(uri)
            results[uri] = _map_post_view(post_view, suppressed_terms)

        for uri in batch:
            if uri not in found_uris:
                results[uri] = {"status": "unavailable", "reason": "not_found"}

    return results
