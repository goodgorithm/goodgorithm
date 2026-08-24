import logging

import requests

from infra.db import UnresolvedAuthorPost
from util.bluesky_appview import APPVIEW_BASE, APPVIEW_REQUEST_TIMEOUT_SECONDS, GET_POSTS_MAX_URIS

logger = logging.getLogger("processing")


def _chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _post_uri(source_id: str) -> str:
    """source_id is `{did}/{rkey}` (ingestion/src/bluesky.ts) -- convert to
    the post's AT-URI, the addressing format app.bsky.feed.getPosts takes.
    Same derivation as moderation_recheck.py's own copy -- not imported
    from there, matching this repo's per-module-owns-its-constants
    convention (moderation_recheck.py itself doesn't import quote_resolver's
    _chunk either; only the genuinely-external-fact constants are shared)."""
    did, _, rkey = source_id.partition("/")
    return f"at://{did}/app.bsky.feed.post/{rkey}"


def _map_author(author) -> dict | None:
    """Same {"displayName", "avatarUrl"} shape quote_resolver.py's
    _map_post_view already produces for a quoted post's author -- reused
    here for a post's *own* author instead, for internal consistency
    between the two Bluesky-author-resolution code paths. None if there's
    genuinely nothing to report (no displayName, no avatar), distinct from
    a dict carrying one field successfully resolved and the other absent."""
    if not isinstance(author, dict):
        return None
    display_name = author.get("displayName")
    avatar = author.get("avatar")
    if not isinstance(display_name, str) and not isinstance(avatar, str):
        return None
    return {
        "displayName": display_name if isinstance(display_name, str) else None,
        "avatarUrl": avatar if isinstance(avatar, str) else None,
    }


def resolve_authors(posts: list[UnresolvedAuthorPost]) -> dict:
    """Resolves a post's own author display name/avatar via Bluesky's
    public AppView -- Jetstream's firehose never carries this, only the
    author's DID, unlike Mastodon whose API response embeds it for free.
    Deliberately scoped by the caller to already-*ranked* posts only, not
    every ingested post -- see infra.db.fetch_bluesky_posts_needing_author_resolution.

    Mirrors moderation_recheck.check_posts' exact batching/failure-
    isolation shape (itself mirroring quote_resolver.resolve_quotes):
    batches into groups of GET_POSTS_MAX_URIS, one getPosts call per
    batch. Never reads likeCount/repostCount/etc. from postView, same
    discipline as quote_resolver.py/moderation_recheck.py.

    Returns {raw_post_id: dict | None} for every post whose batch
    succeeded. A post absent from a successful response (deleted/blocked)
    or with no displayName/avatar to report maps to None -- a definitive
    "no author data available" result, not a failure, so it's not
    retried forever. A post whose batch's HTTP call failed is omitted
    entirely -- the caller re-queries author_resolved_at IS NULL every
    sweep, so an omitted post is naturally retried next time, same
    "no retry loop needed, the sweep itself is the retry" reasoning as
    moderation_recheck.py."""
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
            logger.warning("author resolution failed for a batch of %d posts: %s", len(batch), err)
            continue

        found: set[str] = set()
        for post_view in payload.get("posts", []) if isinstance(payload, dict) else []:
            if not isinstance(post_view, dict):
                continue
            uri = post_view.get("uri")
            if not isinstance(uri, str) or uri not in uri_to_id:
                continue
            found.add(uri)
            results[uri_to_id[uri]] = _map_author(post_view.get("author"))

        for uri in batch:
            if uri not in found:
                results[uri_to_id[uri]] = None

    return results
