import re

# Bluesky's own moderation-service global label values for adult content
# (com.atproto.label.defs), confirmed 2026-08-11. Bluesky can add more
# over time -- this set, not scattered logic, is the place to update.
# Duplicated by hand in ingestion/src/blueskyLabels.ts -- no shared
# package exists across the TS/Python boundary in this repo.
ADULT_LABEL_VALUES = frozenset({"porn", "sexual", "graphic-media", "nudity"})

_HASHTAG_RE = re.compile(r"#(\w+)")


def has_excluded_hashtag(text: str, suppressed_terms: frozenset[str]) -> bool:
    """suppressed_terms is db.fetch_suppressed_terms()'s whole-table read
    (issue #39) -- moderator-curated, loaded fresh once per processing
    cycle, not a module constant, so it can be extended without a code
    change or service restart. Required, not defaulted, so a caller can't
    silently skip the check by forgetting to pass it."""
    return any(tag.lower() in suppressed_terms for tag in _HASHTAG_RE.findall(text))


def has_excluded_spoiler_text(raw_json: dict, suppressed_terms: frozenset[str]) -> bool:
    """Mastodon's spoiler_text (issue #39) is the free-text content-warning
    label a poster writes (e.g. "NSFW", "cw: nsfw") -- just as deliberate a
    self-tag as a hashtag, but not hashtag-formatted, so this matches whole
    words against suppressed_terms rather than _HASHTAG_RE. Bluesky
    raw_json has no spoiler_text key at all, so this is always a no-op for
    Bluesky posts (has_excluded_self_label is Bluesky's equivalent path)."""
    spoiler_text = (raw_json or {}).get("spoiler_text")
    if not isinstance(spoiler_text, str) or not spoiler_text:
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", spoiler_text, re.IGNORECASE) for term in suppressed_terms)


def extract_self_label_values(raw_json: dict) -> list[str]:
    """record.labels.values[].val, defensively -- Jetstream relays whatever
    a client sent with no schema validation (same defensiveness as
    api/src/attachments.ts's isSensitive()). Mastodon rows have no
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
