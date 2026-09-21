import logging

import requests

from infra.db import UncheckedBlueskyPost
from pipeline_stages import content_filter
from util.bluesky_appview import APPVIEW_BASE, APPVIEW_REQUEST_TIMEOUT_SECONDS, GET_POSTS_MAX_URIS

logger = logging.getLogger("processing")


def _chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _post_uri(source_id: str) -> str:
    """source_id is `{did}/{rkey}` (ingestion/src/bluesky.ts) -- convert to
    the post's AT-URI, the addressing format app.bsky.feed.getPosts takes."""
    did, _, rkey = source_id.partition("/")
    return f"at://{did}/app.bsky.feed.post/{rkey}"


def check_posts(posts: list[UncheckedBlueskyPost]) -> dict:
    """Independent backstop against ingestion/'s blueskyLabels.ts real-time
    label-stream listener racing Jetstream's own insert for the same post
    -- batches into groups of GET_POSTS_MAX_URIS, mirroring
    quote_resolver.resolve_quotes' exact batching/failure-isolation shape,
    and checks a post's own current moderation labels (postView.labels --
    redundant with, but independent of, the real-time listener) plus its
    author's profile-level self-label (postView.author.labels). The
    author-label check is the only place a directly-ingested Bluesky
    post's own author's profile self-label gets checked at all --
    Jetstream never carries it at ingestion time. Never reads
    likeCount/repostCount/etc. from postView, same discipline as
    quote_resolver.py.

    Returns {raw_post_id: "excluded" | "bot" | "clean"} for every post
    whose batch succeeded. "excluded" covers an adult-content match
    (ADULT_LABEL_VALUES), a labeler-applied !hide/!warn
    (EXCLUDE_LABEL_VALUES), or the author's own !no-unauthenticated
    self-label -- takes priority over "bot" if a post somehow matches
    both. "bot" (the author's own self-declared bot label, otherwise
    unchecked anywhere for a directly-ingested post) doesn't exclude --
    the caller flips is_bot instead of deleting, since that's a ranking-
    eligibility judgment bot_filter.py already owns, not a content
    exclude. A post absent from a successful response (deleted/blocked/
    never existed) maps to "clean" -- nothing to purge, but still checked
    so it's not re-swept forever. A post whose batch's HTTP call failed is
    omitted entirely -- unlike quote_resolver (raw_posts rows are picked
    up exactly once, so a failure there is permanent), the caller here
    re-queries moderation_checked_at IS NULL every sweep, so an omitted
    post is naturally retried next time rather than lost."""
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
            logger.warning("moderation recheck failed for a batch of %d posts: %s", len(batch), err)
            continue

        found: set[str] = set()
        for post_view in payload.get("posts", []) if isinstance(payload, dict) else []:
            if not isinstance(post_view, dict):
                continue
            uri = post_view.get("uri")
            if not isinstance(uri, str) or uri not in uri_to_id:
                continue
            found.add(uri)
            author = post_view.get("author")
            author_labels = author.get("labels") if isinstance(author, dict) else None
            post_labels = post_view.get("labels")
            if content_filter.has_excluded_bluesky_labels(
                post_labels, author_labels
            ) or content_filter.has_no_unauthenticated_label(author_labels):
                results[uri_to_id[uri]] = "excluded"
            elif content_filter.has_bot_self_label(author_labels):
                results[uri_to_id[uri]] = "bot"
            else:
                results[uri_to_id[uri]] = "clean"

        for uri in batch:
            if uri not in found:
                results[uri_to_id[uri]] = "clean"

    return results
