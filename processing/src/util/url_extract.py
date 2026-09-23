import re

# Shared by dedup.py's near-duplicate URL extraction and
# content_filter.py's/penalties.py's domain-blocklist checks, so none of
# them has to reach into another's internals -- same "shared helper, not
# hand-duplicated" pattern as text_normalize.py living in util/. extract_raw_url returns dedup's single canonical URL;
# extract_all_urls returns every URL a post carries, for the domain checks
# that need to know if ANY of them is on a moderator's list, not just the
# platform-preferred one.

_TEXT_URL_RE = re.compile(r"https?://\S+")


def extract_raw_url(source: str, raw_json: dict, text: str) -> str | None:
    """The first URL a post structurally points to, unnormalized. Prefers
    the platform's own structured embed (Bluesky's embed.external.uri,
    Mastodon's card.url) over a raw-text regex match, falling back to text
    since Mastodon's card is generated asynchronously and is often still
    empty at ingestion time. Callers decide their own normalization --
    dedup.py's extract_dedup_url strips query/fragment and rejects bare-
    domain URLs, content_filter.py's has_excluded_domain does neither
    (a bare marketplace-domain link should still match)."""
    raw_json = raw_json or {}
    if source == "bluesky":
        record = raw_json.get("commit", {}).get("record", {})
        embed = record.get("embed") if isinstance(record, dict) else None
        if isinstance(embed, dict) and embed.get("$type") == "app.bsky.embed.external":
            external = embed.get("external")
            if isinstance(external, dict) and isinstance(external.get("uri"), str):
                return external["uri"]
    elif source == "mastodon":
        card = raw_json.get("card")
        if isinstance(card, dict) and isinstance(card.get("url"), str):
            return card["url"]

    match = _TEXT_URL_RE.search(text)
    return match.group(0) if match else None


def extract_all_urls(source: str, raw_json: dict, text: str) -> list[str]:
    """Every URL a post carries, unnormalized, most-authoritative first: the
    platform's own structured embed/card (if present), then every URL found
    in the free text, in the order they appear. Unlike extract_raw_url, this
    does not stop at the structured embed -- a post's embed and its caption
    text can point to two different places (a link-preview card pointing to
    an unrelated article while the caption itself carries the actual
    monetized/spam link), and a domain-list check needs to see all of them,
    not just the platform-preferred one. Duplicates (the embed URL repeated verbatim in the text,
    or the same text URL posted twice) are removed, preserving first-seen
    order. dedup.py keeps using extract_raw_url -- one canonical URL is the
    right contract for comparing posts against each other, not for "does any
    linked domain match a moderator's list"."""
    raw_json = raw_json or {}
    urls: list[str] = []

    if source == "bluesky":
        record = raw_json.get("commit", {}).get("record", {})
        embed = record.get("embed") if isinstance(record, dict) else None
        if isinstance(embed, dict) and embed.get("$type") == "app.bsky.embed.external":
            external = embed.get("external")
            if isinstance(external, dict) and isinstance(external.get("uri"), str):
                urls.append(external["uri"])
    elif source == "mastodon":
        card = raw_json.get("card")
        if isinstance(card, dict) and isinstance(card.get("url"), str):
            urls.append(card["url"])

    urls.extend(match.group(0) for match in _TEXT_URL_RE.finditer(text or ""))
    return list(dict.fromkeys(urls))
