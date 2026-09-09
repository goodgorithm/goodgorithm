import logging

import requests

from infra.db import ExistenceCheckPost
from util.bluesky_appview import APPVIEW_BASE, APPVIEW_REQUEST_TIMEOUT_SECONDS, GET_POSTS_MAX_URIS

logger = logging.getLogger("processing")


def _chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _post_uri(source_id: str) -> str:
    """source_id is `{did}/{rkey}` (ingestion/src/bluesky.ts) -- convert to
    the post's AT-URI, the addressing format app.bsky.feed.getPosts takes.
    Same derivation as moderation_recheck.py's/author_resolver.py's own
    copies -- this repo's per-module-owns-its-constants convention."""
    did, _, rkey = source_id.partition("/")
    return f"at://{did}/app.bsky.feed.post/{rkey}"


def check_existence(posts: list[ExistenceCheckPost]) -> dict:
    """Re-verifies that each already-ranked Bluesky post still resolves on
    Bluesky's public AppView. A post absent from a *successful* getPosts
    response (user delete, post detach, or the author's account being
    taken down / suspended / deleted -- none of which emit a
    com.atproto.label event) is reported "gone"; the caller deletes its
    raw_posts row.

    Rolling, not one-shot: unlike moderation_recheck.py (which stamps
    moderation_checked_at once, ~1-2 min after a post is scored, and never
    revisits) this sweep re-checks a post repeatedly across its 24h feed
    life -- a takedown usually lands hours after ingestion. It is also the
    processing-side backstop for ingestion/'s real-time Jetstream
    delete/account handling, whose cursorless connection loses any frame
    that arrives during a reconnect.

    Mirrors moderation_recheck.check_posts' / author_resolver.resolve_authors'
    exact batching/failure-isolation shape: batches into groups of
    GET_POSTS_MAX_URIS, one getPosts call per batch. Reads only
    post_view["uri"] -- never likeCount/repostCount/etc., same discipline
    as the sibling sweeps.

    Returns {raw_post_id: "present" | "gone"} for every post whose batch
    succeeded. A post whose batch's HTTP call failed is omitted entirely --
    the caller re-queries every sweep, so an omitted post is naturally
    retried next time rather than deleted on a transient AppView error."""
    uri_to_id = {_post_uri(p.source_id): p.raw_post_id for p in posts}
    results: dict = {}

    for batch in _chunk(list(uri_to_id.keys()), GET_POSTS_MAX_URIS):
        try:
            response = requests.get(
                f"{APPVIEW_BASE}/app.bsky.feed.getPosts",
                params=[("uris", uri) for uri in batch],
                timeout=APPVIEW_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as err:
            logger.warning("existence recheck failed for a batch of %d posts: %s", len(batch), err)
            continue

        found: set[str] = set()
        for post_view in payload.get("posts", []) if isinstance(payload, dict) else []:
            if not isinstance(post_view, dict):
                continue
            uri = post_view.get("uri")
            if not isinstance(uri, str) or uri not in uri_to_id:
                continue
            found.add(uri)
            results[uri_to_id[uri]] = "present"

        for uri in batch:
            if uri not in found:
                results[uri_to_id[uri]] = "gone"

    return results
