import logging

import requests

import content_filter

logger = logging.getLogger("processing")

# Public, unauthenticated, generously-rate-limited per Bluesky's own docs
# ("cached... intended for public web use cases") -- api/'s architecture
# stays untouched (stateless DB-in/JSON-out); this is processing/'s first
# outbound network dependency, deliberately kept there rather than in
# api/ so quoted content can be content-filtered before it's ever exposed.
APPVIEW_BASE = "https://public.api.bsky.app/xrpc"
GET_POSTS_MAX_URIS = 25  # app.bsky.feed.getPosts' documented max per call
REQUEST_TIMEOUT_SECONDS = 10


def extract_quote_uri(raw_json: dict) -> str | None:
    """Pulls the quoted post's AT-URI out of a Bluesky commit's embed, if
    any -- mirrors api/src/attachments.ts's parseBlueskyQuote/recordWithMedia
    nesting exactly (direct quote: embed.record.uri; recordWithMedia: one
    level deeper at embed.record.record.uri, confirmed against a real row
    during the original attachments work). Only returns URIs that point at
    an actual post, not a list/starter-pack/feed-generator quote."""
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


def _map_post_view(post_view: dict) -> dict:
    """Maps a hydrated postView into the exact display shape api/ serves
    verbatim. Never reads likeCount/repostCount/replyCount/quoteCount/
    bookmarkCount even though they're required/standard fields on
    postView -- deliberate (Decisions Log: no engagement signals anywhere
    in the product, not just ranking), not an oversight."""
    author = post_view.get("author")
    record = post_view.get("record")
    text = record.get("text") if isinstance(record, dict) else None
    if not isinstance(author, dict) or not isinstance(text, str):
        return {"status": "unavailable", "reason": "not_found"}

    # Same checks a regular post gets before it's ever stored, applied
    # here to the quoted post's own text/self-labels -- a quoted post
    # carries its own moderation status independent of the outer post
    # quoting it (Decisions Log: precision over recall).
    if content_filter.is_content_excluded(text, {"commit": {"record": record}}):
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


def resolve_quotes(uris: list[str]) -> dict[str, dict]:
    """Batches into groups of 25 (getPosts' documented max), calls
    Bluesky's public getPosts endpoint. Never crashes the calling cycle --
    a failed batch (network error, non-200, timeout) just omits those URIs
    from the returned dict entirely, which pipeline.py treats as
    quote_content staying null for those posts this cycle, same as any
    other not-yet-resolved case. No retry-next-cycle: each raw_post is
    scored exactly once, so a miss here permanently falls back to the
    plain quote-link card for that post -- acceptable given the endpoint's
    documented high availability and generous rate limits.

    A URI genuinely absent from a *successful* response (deleted, blocked,
    or detached -- getPosts doesn't distinguish which) maps to an explicit
    {"status": "unavailable", "reason": "not_found"}, distinct from a
    network failure: this is a real, known answer, not a missing one.
    """
    results: dict[str, dict] = {}
    unique_uris = list(dict.fromkeys(uris))  # de-dupe, preserve order

    for batch in _chunk(unique_uris, GET_POSTS_MAX_URIS):
        try:
            response = requests.get(
                f"{APPVIEW_BASE}/app.bsky.feed.getPosts",
                params=[("uris", uri) for uri in batch],
                timeout=REQUEST_TIMEOUT_SECONDS,
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
            results[uri] = _map_post_view(post_view)

        for uri in batch:
            if uri not in found_uris:
                results[uri] = {"status": "unavailable", "reason": "not_found"}

    return results
