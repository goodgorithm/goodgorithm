import re

import config

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


def is_content_excluded(text: str, raw_json: dict, suppressed_terms: frozenset[str]) -> bool:
    return (
        has_excluded_hashtag(text, suppressed_terms)
        or has_excluded_self_label(raw_json)
        or has_excluded_spoiler_text(raw_json, suppressed_terms)
    )
