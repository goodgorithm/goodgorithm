import re

# Moved out of dedup.py (was a private _extract_raw_url) so content_filter.py
# can reuse the same platform-specific extraction for its own domain
# blocklist check (issue #57) without reaching into another pipeline
# stage's internals -- same "shared helper, not hand-duplicated" precedent
# as sentiment_model.py/text_normalize.py's own move into util/.

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
