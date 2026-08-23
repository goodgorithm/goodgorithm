import re

# Pure stdlib, zero project imports — same discipline as sentiment_model.py,
# and for the same reason: this file is imported both by the category
# classifier's training notebook (via a commit-pinned raw GitHub URL) and by
# processing/'s inference path, so text normalization can never drift
# between train and inference even though the two run in different
# environments.

_URL_RE = re.compile(r"https?://\S+")
_MENTION_RE = re.compile(r"@[\w.-]+")
_WHITESPACE_RE = re.compile(r"\s+")
_HASHTAG_RE = re.compile(r"#(\w+)")
_CAMEL_BOUNDARY_RE = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[a-zA-Z])(?=[0-9])|(?<=[0-9])(?=[a-zA-Z])"
)


def split_camel_hashtags(text: str) -> str:
    """#OfCourseItsGenocide -> ". Of Course Its Genocide" -- issue #70.
    Every word-level stage (TF-IDF, NER, category classification) used to
    see a hashtag as one opaque glued token.

    The leading ". " (not just a space) is load-bearing, confirmed by real
    A/B testing against production posts: without it, adjacent hashtags
    lose their separation and spaCy's NER glues them into one garbage
    multi-word entity (e.g. 6 actor-name hashtags merging into 2 unreadable
    strings). With it, the same 6 hashtags resolve to 6 correctly-typed
    PERSON entities.

    Known limitation, not fixed: a 2-letter acronym directly followed by an
    all-lowercase word (#UKnews, as opposed to #UKNews) has no case
    transition marking where the second word starts, so this produces a
    spurious split between the acronym's own two letters instead
    ("UKnews" -> "U Knews", not "UK news") -- would need a dictionary-based
    splitter (e.g. wordninja), not a regex, to close this.

    Must run before lowercasing -- callers needing NER-quality output
    (case-sensitive) should call this directly; normalize_text() calls it
    first, before its own lowercasing, for TF-IDF/category/taxonomy use."""
    return _HASHTAG_RE.sub(lambda m: ". " + _CAMEL_BOUNDARY_RE.sub(" ", m.group(1)), text)


def normalize_text(text: str) -> str:
    text = split_camel_hashtags(text)
    text = text.lower()
    text = _URL_RE.sub(" ", text)
    text = _MENTION_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()
