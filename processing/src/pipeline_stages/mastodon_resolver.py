"""Resolves a Mastodon structured reply's parent -- the one context.py
target that genuinely needs a Mastodon-side lookup (quote-inline/RE:
targets are Bluesky posts, resolved by quote_resolver.py instead). Mirrors
quote_resolver.py's shape (extract a target, resolve a batch into the same
QuoteContent-family dict), so pipeline.resolve_context() can treat either
resolver uniformly. See CLAUDE.md's Post attachments & embeds section and
the wiki's Mastodon page.
"""

import html as html_module
import logging
import os
import re

import requests

from pipeline_stages import content_filter

logger = logging.getLogger("processing")

MASTODON_STATUS_REQUEST_TIMEOUT_SECONDS = int(os.environ.get("MASTODON_STATUS_REQUEST_TIMEOUT_SECONDS", "10"))

# Matches ingestion/'s own User-Agent convention for outbound requests to
# third-party Mastodon instances.
_USER_AGENT = "Goodgorithm/0.1 (https://github.com/goodgorithm)"

_BLOCK_TAGS_RE = re.compile(r"</?(p|br|div|li|ul|ol|blockquote)\b[^>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(raw_html: str) -> str:
    """Simplified Python port of ingestion/src/mastodon.ts's stripHtml --
    block-tag spacing plus tag stripping, using stdlib html.unescape()
    for entities instead of porting that file's hand-rolled entity table.
    Deliberately not full-fidelity (skips truncated-link recovery): this
    text feeds scoring/display of a resolved parent, not primary
    ingestion, so exact parity isn't required. Kept in sync by hand, same
    cross-language-boundary precedent as util/sentiment_model.py's
    tokenizer -- see CLAUDE.md's Sentiment model loading section."""
    with_breaks = _BLOCK_TAGS_RE.sub(" ", raw_html)
    without_tags = _TAG_RE.sub("", with_breaks)
    decoded = html_module.unescape(without_tags)
    return re.sub(r"\s+", " ", decoded).strip()


def extract_reply_target(raw_json: dict, author_id: str) -> str | None:
    """{polled_instance}/{status_id} -- self-contained, mirrors an AT-URI
    embedding its own DID. polled_instance comes from author_id
    ({polled_instance}/{acct}, ingestion/'s own convention for a Mastodon
    row), never from raw_json -- a status API response never names the
    instance that served it. Only the direct parent -- issue #291, not
    this pass."""
    reply_id = (raw_json or {}).get("in_reply_to_id")
    if not isinstance(reply_id, str) or not reply_id:
        return None
    instance = (author_id or "").split("/", 1)[0]
    if not instance:
        return None
    return f"{instance}/{reply_id}"


def _is_discoverable(account: dict) -> bool:
    """Simplified Python port of ingestion/src/mastodon.ts's isDiscoverable
    -- same null/undefined-counts-as-opted-in discipline, same inverted
    polarity on noindex. Needed here (unlike a directly-ingested post,
    which isDiscoverable already gated before it ever reached raw_posts)
    because a resolved reply target's account never went through
    ingestion/'s own filtering -- it's a different account than the one
    that was actually polled."""
    return (
        account.get("discoverable") is not False
        and account.get("indexable") is not False
        and account.get("noindex") is not True
    )


def _map_status(status: dict, suppressed_terms: frozenset[str], suppressed_domains: frozenset[str]) -> dict:
    content = status.get("content")
    account = status.get("account")
    if not isinstance(content, str) or not isinstance(account, dict):
        return {"status": "unavailable", "reason": "not_found"}

    text = _strip_html(content)

    # Same checks a regular Mastodon post gets before it's ever stored --
    # status is already shaped like a stored row's raw_json (same API),
    # so it's passed straight through, no reconstruction needed. The
    # discoverable/indexable/noindex/bot checks below are the resolved
    # target's own account, not the referencing post's -- see
    # _is_discoverable's docstring for why this needs checking here at
    # all.
    if content_filter.is_content_excluded("mastodon", text, status, suppressed_terms, suppressed_domains):
        return {"status": "unavailable", "reason": "filtered"}

    if not _is_discoverable(account) or account.get("bot") is True:
        return {"status": "unavailable", "reason": "filtered"}

    display_name = account.get("display_name")
    acct = account.get("acct") or account.get("username")
    avatar = account.get("avatar")
    created_at = status.get("created_at")
    url = status.get("url")

    return {
        "status": "available",
        "author": {
            "displayName": display_name if isinstance(display_name, str) and display_name else None,
            "handle": acct if isinstance(acct, str) and acct else None,
            "avatarUrl": avatar if isinstance(avatar, str) else None,
        },
        "text": text,
        "createdAt": created_at if isinstance(created_at, str) else None,
        # Mastodon's own canonical permalink for the status -- unlike a
        # Bluesky AT-URI, a status id alone (even qualified by instance)
        # isn't a real URL without the author's username, which we don't
        # have without this live fetch. api/'s only source for the
        # attachment's clickable url on a Mastodon-target reply. See
        # CLAUDE.md's Post attachments & embeds section.
        "url": url if isinstance(url, str) else None,
    }


def resolve_context(
    targets: list[str], suppressed_terms: frozenset[str], suppressed_domains: frozenset[str]
) -> tuple[dict[str, dict], dict[str, str]]:
    """targets are {instance}/{status_id} strings (extract_reply_target).
    One request per target -- Mastodon's GET /api/v1/statuses/:id has no
    batch-lookup endpoint like Bluesky's getPosts, and each target can be
    on a different instance anyway. Never crashes the calling cycle -- a
    failed request just omits that target from the returned dicts
    entirely, naturally retried on the next sweep since
    fetch_context_pending() re-selects anything still 'pending'. A 404
    maps to an explicit not_found status instead.

    Returns (content_by_target, author_id_by_target) -- the second dict
    is a side channel for the caller's own is_bot verdict lookup,
    populated only for "available" results, qualified to the same
    {acct}@{instance} shape canonical_account_id normalizes to. This is
    best-effort, not full cross-instance canonicalization: it only finds
    a match when that account is also one we've independently ingested
    via one of our own polled instances under the exact raw
    {instance}/{acct} shape db.recent_bot_verdict compares against."""
    results: dict[str, dict] = {}
    author_ids: dict[str, str] = {}

    for target in dict.fromkeys(targets):  # de-dupe, preserve order
        instance, _, status_id = target.partition("/")
        if not instance or not status_id:
            continue
        try:
            response = requests.get(
                f"https://{instance}/api/v1/statuses/{status_id}",
                timeout=MASTODON_STATUS_REQUEST_TIMEOUT_SECONDS,
                headers={"User-Agent": _USER_AGENT},
            )
            if response.status_code == 404:
                results[target] = {"status": "unavailable", "reason": "not_found"}
                continue
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as err:
            logger.warning("mastodon status resolution failed for %s: %s", target, err)
            continue

        if not isinstance(payload, dict):
            results[target] = {"status": "unavailable", "reason": "not_found"}
            continue

        results[target] = _map_status(payload, suppressed_terms, suppressed_domains)

        account = payload.get("account")
        acct = account.get("acct") or account.get("username") if isinstance(account, dict) else None
        if isinstance(acct, str) and acct:
            author_ids[target] = acct if "@" in acct else f"{acct}@{instance}"

    return results, author_ids
