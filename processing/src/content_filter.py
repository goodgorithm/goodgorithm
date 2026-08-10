import re

# Deliberately narrow and hand-curated -- precision over recall (Decisions
# Log, 2026-08-11). Only hashtags that function as an unambiguous
# self-tagging convention for adult content, not identity/topic terms that
# merely correlate with it in some posts (e.g. NOT "lesbian" -- that's an
# identity term, hard-excluding it would flag ordinary LGBTQ+ content as
# adult, a discrimination risk, not a precision win). Extend by adding
# more unambiguous values here -- no matching logic changes needed.
EXCLUDED_HASHTAGS = frozenset({"nsfw"})

# Bluesky's own moderation-service global label values for adult content
# (com.atproto.label.defs), confirmed 2026-08-11. Bluesky can add more
# over time -- this set, not scattered logic, is the place to update.
# Duplicated by hand in ingestion/src/blueskyLabels.ts -- no shared
# package exists across the TS/Python boundary in this repo.
ADULT_LABEL_VALUES = frozenset({"porn", "sexual", "graphic-media", "nudity"})

_HASHTAG_RE = re.compile(r"#(\w+)")


def has_excluded_hashtag(text: str) -> bool:
    return any(tag.lower() in EXCLUDED_HASHTAGS for tag in _HASHTAG_RE.findall(text))


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


def is_content_excluded(text: str, raw_json: dict) -> bool:
    return has_excluded_hashtag(text) or has_excluded_self_label(raw_json)
