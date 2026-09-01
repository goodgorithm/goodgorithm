import os
import re
from urllib.parse import urlsplit

import config
from util import bluesky_funnel
from util.url_extract import extract_raw_url

# Bluesky's own global label values -- not moderator-curated like
# suppressed_terms below. Sourced from config.BLUESKY_ADULT_LABEL_VALUES
# (same env var name as ingestion/'s blueskyLabels.ts, own copy). Also
# used directly by quote_resolver.py for the same check against a
# resolved quote's labels. See the wiki's Bluesky Protocol and Pipeline
# Internals pages.
ADULT_LABEL_VALUES = config.BLUESKY_ADULT_LABEL_VALUES

# How many adult/funnel hashtags (util/bluesky_funnel.py's vocabulary, or
# the live suppressed_terms table) a Bluesky post must carry ALONGSIDE a
# funnel call-to-action phrase for has_bluesky_funnel_shape to hard-exclude
# it. Validated against a 24h production sample (zero false positives at
# 4-6) -- the same "confirm high-precision, then hard-exclude" bar as
# has_excluded_sensitive_media. The account-cluster flag in
# infra/network_detector.py runs a deliberately looser threshold; see its
# comment for why.
FUNNEL_MIN_ADULT_HASHTAGS = int(os.environ.get("CONTENT_FILTER_FUNNEL_MIN_ADULT_HASHTAGS", "5"))

_HASHTAG_RE = re.compile(r"#(\w+)")


def has_excluded_hashtag(text: str, suppressed_terms: frozenset[str]) -> bool:
    """suppressed_terms is db.fetch_suppressed_terms()'s whole-table read --
    moderator-curated, refreshed periodically via db.fetch_moderation_lists()'s
    cache, not a module constant. Required, not defaulted, so a caller
    can't silently skip the check by forgetting to pass it. See the wiki's
    Content Filtering page."""
    return any(tag.lower() in suppressed_terms for tag in _HASHTAG_RE.findall(text))


def has_excluded_spoiler_text(raw_json: dict, suppressed_terms: frozenset[str]) -> bool:
    """Mastodon's spoiler_text -- a free-text content-warning label, not
    hashtag-formatted, so this matches suppressed_terms as whole words
    rather than via _HASHTAG_RE. See the wiki's Content Filtering page."""
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


def has_excluded_sensitive_media(raw_json: dict) -> bool:
    """Mastodon's sensitive flag, narrowed to the one sub-case confirmed
    high-precision for adult content: media attached AND no spoiler_text.
    The flag alone is too blunt to hard-exclude on -- a post with no media
    (or with a spoiler_text) is far more likely to be ordinary CW-culture
    use (movie/game spoilers, political discussion, mental-health
    disclosure, courtesy "eye contact" selfie tags) than adult content,
    and excluding on the flag alone would wrongly catch genuinely positive
    content along with it. Bluesky rows have no top-level "sensitive"/
    "media_attachments" keys at all (its adult content is already
    hard-excluded via has_excluded_self_label above), so this naturally
    returns False for them. See CLAUDE.md's Content moderation section."""
    raw_json = raw_json or {}
    if raw_json.get("sensitive") is not True:
        return False
    media_attachments = raw_json.get("media_attachments")
    if not isinstance(media_attachments, list) or not media_attachments:
        return False
    return not raw_json.get("spoiler_text")


def matches_domain_list(candidate: str, domains: frozenset[str]) -> bool:
    """Exact or subdomain match (smile.amazon.com, www.amazon.com both
    match an amazon.com entry) -- the shared "does this domain match a
    moderator's list entry" primitive, used by has_excluded_domain (a
    post's linked URL) and has_excluded_home_instance (a Mastodon account's
    home server) below over suppressed_domains, and by
    aggregator_demote.py over the separate aggregator_instances list."""
    return candidate in domains or any(candidate.endswith("." + domain) for domain in domains)


def has_excluded_domain(source: str, raw_json: dict, text: str, suppressed_domains: frozenset[str]) -> bool:
    """suppressed_domains is db.fetch_suppressed_domains()'s whole-table read
    -- same moderator-curated, periodically-refreshed-via-cache contract as
    suppressed_terms. Deliberately doesn't reuse dedup.py's
    extract_dedup_url -- that rejects bare-domain URLs (no path), right for
    dedup (a homepage link is a weak dedup signal) but wrong here (a bare
    https://www.amazon.com link should still match)."""
    raw_url = extract_raw_url(source, raw_json, text)
    if not raw_url:
        return False
    try:
        netloc = urlsplit(raw_url).netloc.lower()
    except ValueError:
        return False
    return matches_domain_list(netloc, suppressed_domains)


def has_bluesky_funnel_shape(source: str, text: str, suppressed_terms: frozenset[str]) -> bool:
    """Bluesky-only: a coordinated OnlyFans/"funnel" post -- a funnel
    call-to-action phrase in the caption ("...in my bio", "one tap away",
    ...) AND at least FUNNEL_MIN_ADULT_HASHTAGS hashtags drawn from
    util/bluesky_funnel.py's adult/funnel vocabulary or the live
    suppressed_terms table. Neither half alone is safe to hard-exclude on:
    the CTA phrase is heavily used by musicians / comic creators / support
    services, and the individual hashtags are ordinary goth / cosplay /
    fitness vocabulary -- but the conjunction had zero false positives
    across a 24h production sample. Mastodon rows never match (source
    guard). suppressed_terms is already threaded through
    is_content_excluded, so this needs no new argument. See the wiki's
    Content Filtering page, and infra/network_detector.py for the
    account-level flag that shares this same vocabulary."""
    if source != "bluesky":
        return False
    if not bluesky_funnel.has_funnel_cta(text):
        return False
    return bluesky_funnel.count_adult_funnel_hashtags(text, suppressed_terms) >= FUNNEL_MIN_ADULT_HASHTAGS


def has_excluded_home_instance(raw_json: dict, suppressed_domains: frozenset[str]) -> bool:
    """Mastodon-only: excludes every post from an account whose own home
    instance is a listed domain -- distinct from has_excluded_domain
    above, which only matches a link *inside* the post body/card. Many
    adult-content posts carry no outbound link at all (native image posts),
    so a link-domain check alone can't catch a post that merely originates
    from a fully dedicated adult instance. Reuses suppressed_domains
    rather than a separate table: a moderator adding a domain there
    reasonably expects both "links to this domain" and "accounts hosted on
    this domain" to be covered, with identical exact/subdomain matching.
    Mastodon's account.acct is "user" for a local account or "user@host"
    for a remote one (federated into one of our polled instances' public
    timelines) -- only the "@host" form has a home instance to check.
    Bluesky has no per-instance federation concept, so raw_json here always
    lacks an "account" key in this shape and this naturally returns False."""
    account = (raw_json or {}).get("account")
    acct = account.get("acct") if isinstance(account, dict) else None
    if not isinstance(acct, str) or "@" not in acct:
        return False
    home_instance = acct.rsplit("@", 1)[-1].lower()
    return matches_domain_list(home_instance, suppressed_domains)


def is_content_excluded(
    source: str, text: str, raw_json: dict, suppressed_terms: frozenset[str], suppressed_domains: frozenset[str]
) -> bool:
    return (
        has_excluded_hashtag(text, suppressed_terms)
        or has_bluesky_funnel_shape(source, text, suppressed_terms)
        or has_excluded_self_label(raw_json)
        or has_excluded_spoiler_text(raw_json, suppressed_terms)
        or has_excluded_domain(source, raw_json, text, suppressed_domains)
        or has_excluded_sensitive_media(raw_json)
        or has_excluded_home_instance(raw_json, suppressed_domains)
    )
