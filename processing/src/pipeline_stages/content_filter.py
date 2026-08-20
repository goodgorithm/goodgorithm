import re
from urllib.parse import urlsplit

import config
from util.url_extract import extract_raw_url

# Bluesky's own global label values -- not moderator-curated like
# suppressed_terms below. Sourced from config.BLUESKY_ADULT_LABEL_VALUES
# (same env var name as ingestion/'s blueskyLabels.ts, own copy). Also
# used directly by quote_resolver.py for the same check against a
# resolved quote's labels. See the wiki's Bluesky Protocol and Pipeline
# Internals pages.
ADULT_LABEL_VALUES = config.BLUESKY_ADULT_LABEL_VALUES

_HASHTAG_RE = re.compile(r"#(\w+)")


def has_excluded_hashtag(text: str, suppressed_terms: frozenset[str]) -> bool:
    """suppressed_terms is db.fetch_suppressed_terms()'s whole-table read --
    moderator-curated, loaded fresh once per cycle, not a module constant.
    Required, not defaulted, so a caller can't silently skip the check by
    forgetting to pass it. See the wiki's Pipeline Internals page."""
    return any(tag.lower() in suppressed_terms for tag in _HASHTAG_RE.findall(text))


def has_excluded_spoiler_text(raw_json: dict, suppressed_terms: frozenset[str]) -> bool:
    """Mastodon's spoiler_text -- a free-text content-warning label, not
    hashtag-formatted, so this matches suppressed_terms as whole words
    rather than via _HASHTAG_RE. See the wiki's Pipeline Internals page."""
    spoiler_text = (raw_json or {}).get("spoiler_text")
    if not isinstance(spoiler_text, str) or not spoiler_text:
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", spoiler_text, re.IGNORECASE) for term in suppressed_terms)


def extract_self_label_values(raw_json: dict) -> list[str]:
    """record.labels.values[].val, defensively -- Jetstream relays whatever
    a client sent with no schema validation. Mastodon rows have no
    "commit" key at all, so this naturally returns []."""
    record = (raw_json or {}).get("commit", {}).get("record", {})
    labels = record.get("labels") if isinstance(record, dict) else None
    values = labels.get("values") if isinstance(labels, dict) else None
    if not isinstance(values, list):
        return []
    return [v.get("val") for v in values if isinstance(v, dict) and isinstance(v.get("val"), str)]


def has_excluded_self_label(raw_json: dict) -> bool:
    return any(v in ADULT_LABEL_VALUES for v in extract_self_label_values(raw_json))


def has_excluded_domain(source: str, raw_json: dict, text: str, suppressed_domains: frozenset[str]) -> bool:
    """suppressed_domains is db.fetch_suppressed_domains()'s whole-table read
    -- same moderator-curated, loaded-fresh-per-cycle contract as
    suppressed_terms (issue #57). Deliberately doesn't reuse dedup.py's
    extract_dedup_url -- that rejects bare-domain URLs (no path), right for
    dedup (a homepage link is a weak dedup signal) but wrong here (a bare
    https://www.amazon.com link should still match). Matches a listed
    domain exactly or as a subdomain (smile.amazon.com, www.amazon.com both
    match an amazon.com entry) -- the natural expectation for a moderator
    entering a bare domain."""
    raw_url = extract_raw_url(source, raw_json, text)
    if not raw_url:
        return False
    try:
        netloc = urlsplit(raw_url).netloc.lower()
    except ValueError:
        return False
    return netloc in suppressed_domains or any(netloc.endswith("." + domain) for domain in suppressed_domains)


def is_content_excluded(
    source: str, text: str, raw_json: dict, suppressed_terms: frozenset[str], suppressed_domains: frozenset[str]
) -> bool:
    return (
        has_excluded_hashtag(text, suppressed_terms)
        or has_excluded_self_label(raw_json)
        or has_excluded_spoiler_text(raw_json, suppressed_terms)
        or has_excluded_domain(source, raw_json, text, suppressed_domains)
    )
