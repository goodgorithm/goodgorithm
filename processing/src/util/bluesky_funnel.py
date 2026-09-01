import re

# The funnel call-to-action phrases and the adult/funnel hashtag
# vocabulary that together identify the coordinated Bluesky "funnel"
# network -- image + short coy caption + a bag of rotating hashtags + an
# "...in my bio" call to action, dozens of accounts. One copy here so
# content_filter.has_bluesky_funnel_shape (the per-post hard exclude) and
# infra/network_detector's account-cluster flag can't drift. Lives in
# util/ -- the same "shared helper, not hand-duplicated" placement as
# text_normalize.py / url_extract.py -- because infra/db.py must not reach
# up into pipeline_stages/.
#
# The vocabulary is code, not a moderator table: neither half is safe to
# act on alone (the CTA phrase is heavily used by musicians, comic
# creators, artists and support services; the individual hashtags are
# ordinary goth / cosplay / fitness vocabulary), so this is only ever
# evaluated as the CONJUNCTION of a CTA phrase and a hashtag-count
# threshold. Tuning either set is a reviewed-against-data change, same as
# language_filter's detector choice.

# Funnel call-to-action substrings, matched case-insensitively against a
# post's caption with hashtags stripped. MUST stay within the common
# subset of Python `re` and Postgres POSIX ARE (network_detector's
# aggregate feeds FUNNEL_CTA_PATTERN straight to `~*`): plain alternation,
# grouping, literals and `?` only -- no `\b`, no lookaround, no `[[:...:]]`
# classes.
FUNNEL_CTA_PHRASES = (
    "in my bio",
    "link in bio",
    "check my bio",
    "peek at my bio",
    "my bio knows",
    "bio does the talking",
    "good stuff lives in my bio",
    "the answer is sitting in my bio",
    "rest is in my bio",
    "one tap away",
    "spicy half",
    "everything i cannot post here",
    "not posting it twice",
    "find me on (fansly|onlyfans|twit)",
)

# Shared verbatim by the Python regex below and the SQL `~*` operator.
FUNNEL_CTA_PATTERN = "(" + "|".join(FUNNEL_CTA_PHRASES) + ")"

_FUNNEL_CTA_RE = re.compile(FUNNEL_CTA_PATTERN, re.IGNORECASE)

# Same shape as content_filter._HASHTAG_RE; a private copy because util/ is
# below pipeline_stages/ in the import graph.
_HASHTAG_RE = re.compile(r"#(\w+)")

# The corroborating hashtag vocabulary. DELIBERATELY broader than anything
# allowed in the suppressed_terms table -- several of these (`curvy`,
# `bikini`, `cosplaygirl`, `gothgirl`, `gymgirl`, `tattooedgirl`,
# `altstyle`) are also legitimate goth / cosplay / fitness / body-positive
# vocabulary, which is exactly why suppressed_terms (an exact one-tag-at-a-
# time hard exclude) must not carry them. Here they only ever count toward
# a threshold that also requires a funnel CTA phrase, which neutralises the
# per-tag ambiguity. The live suppressed_terms set is unioned onto this at
# check time (see count_adult_funnel_hashtags), so a moderator topping up
# that table also strengthens this signal.
ADULT_FUNNEL_HASHTAGS = frozenset(
    {
        "egirl", "egirlstyle", "hotgirl", "hotgirls", "fitmodel", "fitbabe", "fitgirl",
        "gymgirl", "tattooedgirl", "inkedgirl", "inkedmodel", "inkedbabe", "gothgirl",
        "gothbabe", "altgirl", "altmodel", "altstyle", "alternativegirl", "curvygirl",
        "curvymodel", "curvy", "curves", "thicc", "thickthighs", "palegirl", "babygirl",
        "dreamgirl", "bombshell", "temptress", "vixen", "seductress", "sultry",
        "seductive", "teasing", "sensual", "siren", "foxy", "knockout", "stunner",
        "hottie", "diva", "goddess", "allure", "kittenish", "bratty", "pinup",
        "bodysuit", "fishnets", "thighhighs", "wetlook", "latex", "lingerie", "boudoir",
        "spoiled", "cosplaygirl", "bikini",
    }
)


def strip_hashtags(text: str) -> str:
    return _HASHTAG_RE.sub("", text)


def has_funnel_cta(text: str) -> bool:
    """True when a funnel CTA phrase appears in `text` after hashtags are
    stripped -- so a glued `#linkinbio` tag never counts (the phrases are
    spaced), only real caption prose does."""
    return _FUNNEL_CTA_RE.search(strip_hashtags(text)) is not None


def count_adult_funnel_hashtags(text: str, extra_terms: frozenset[str]) -> int:
    """Number of distinct hashtags in `text` that are in
    ADULT_FUNNEL_HASHTAGS or in `extra_terms` (the live suppressed_terms
    set, passed straight through from is_content_excluded)."""
    tags = {t.lower() for t in _HASHTAG_RE.findall(text)}
    return len(tags & (ADULT_FUNNEL_HASHTAGS | extra_terms))
