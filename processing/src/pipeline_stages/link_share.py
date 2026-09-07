"""Down-weights a "bare link-share" in ranking: a post carrying a link
card whose own text adds nothing beyond the card's own title -- a
WordPress/Buffer/dlvr.it/RSS auto-crosspost, or a manual "here's a link"
with no take of its own. Low-value in the feed but not bad content (some
are genuine must-read reshares), so this produces a base_score
devaluation, not a hard exclude like content_filter/context_dependency.
See the wiki's Ranking page.

There's no structural "this is a link-share" marker on either platform --
Mastodon's card.type is "link" for a personal blog, a news story and a
YouTube video alike -- so the signal is behavioral: the author's own words
(URLs and hashtags stripped) add nothing beyond the card title (empty, a
verbatim substring, or a near-subset of its words), or there's no card at
all but a link plus a short hashtag-bag caption. See classify().
"""

import os
import re
from dataclasses import dataclass

# base_score multiplier for a bare link-share -- same default as
# context_dependency.py's Bluesky reply devalue. See the wiki's Ranking page.
LINK_SHARE_DEVALUE_MULTIPLIER = float(os.environ.get("LINK_SHARE_DEVALUE_MULTIPLIER", "0.4"))
if not 0.0 < LINK_SHARE_DEVALUE_MULTIPLIER <= 1.0:
    raise ValueError(
        f"LINK_SHARE_DEVALUE_MULTIPLIER ({LINK_SHARE_DEVALUE_MULTIPLIER}) must be in (0.0, 1.0]"
    )

# A post that adds a real sentence of its own isn't a bare share even if
# it also pastes the headline. Above this many non-URL/non-hashtag chars,
# never devalue regardless of the substring / overlap check.
LINK_SHARE_MAX_ORIGINAL_CHARS = int(os.environ.get("LINK_SHARE_MAX_ORIGINAL_CHARS", "200"))

# Fuzzy fallback to the verbatim-substring check: the fraction of the
# author's own words (length > 2) that also appear in the card title. A
# restated headline with a trailing hashtag/emoji clears this without being
# a substring.
LINK_SHARE_TITLE_OVERLAP_RATIO = float(os.environ.get("LINK_SHARE_TITLE_OVERLAP_RATIO", "0.85"))

# Card-independent trigger for shortener/RSS promo that carries no link
# card at all: a link is present, the author's own words are at most this
# many chars, and they're mostly a hashtag bag (hashtags / word count at or
# above the ratio). This one deliberately catches some genuine one-line
# hashtag-heavy human shares -- the hashtag-bag gate keeps a plain
# "Happy birthday X! <link>" (no hashtags) out.
LINK_SHARE_THIN_CAPTION_CHARS = int(os.environ.get("LINK_SHARE_THIN_CAPTION_CHARS", "35"))
LINK_SHARE_HASHTAG_BAG_RATIO = float(os.environ.get("LINK_SHARE_HASHTAG_BAG_RATIO", "0.3"))

_URL_RE = re.compile(r"https?://\S+")
_HASHTAG_RE = re.compile(r"#\w+")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class LinkShareClassification:
    is_bare_link_share: bool
    devalue_multiplier: float = 1.0  # base_score multiplier; 1.0 == no penalty


def _card_title(source: str, raw_json: dict) -> str | None:
    """The link card's own title, or None if the post carries no link card.
    Same structured-embed shape as util/url_extract.extract_raw_url, read
    defensively hop by hop."""
    raw_json = raw_json or {}
    if source == "bluesky":
        record = raw_json.get("commit", {}).get("record", {})
        embed = record.get("embed") if isinstance(record, dict) else None
        if isinstance(embed, dict) and embed.get("$type") == "app.bsky.embed.external":
            external = embed.get("external")
            if isinstance(external, dict) and isinstance(external.get("title"), str):
                return external["title"]
    elif source == "mastodon":
        card = raw_json.get("card")
        if isinstance(card, dict) and isinstance(card.get("title"), str):
            return card["title"]
    return None


def _strip(text: str) -> str:
    """The author's own words: URLs and hashtags removed, whitespace
    collapsed, casefolded. Deliberately not util/text_normalize.normalize_text
    -- that expands #DallasCowboys into "dallas cowboys" words rather than
    removing the hashtag, which would break the substring check for a
    genuine bare share."""
    text = _URL_RE.sub(" ", text or "")
    text = _HASHTAG_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip().casefold()


def _hashtag_ratio(text: str) -> float:
    words = text.split()
    return len(_HASHTAG_RE.findall(text)) / len(words) if words else 0.0


def _title_overlap(stripped: str, normalized_title: str) -> float:
    caption_words = [w for w in stripped.split() if len(w) > 2]
    if not caption_words:
        return 0.0
    title_words = set(normalized_title.split())
    return sum(1 for w in caption_words if w in title_words) / len(caption_words)


def _bare(reason: bool) -> LinkShareClassification:
    if reason:
        return LinkShareClassification(is_bare_link_share=True, devalue_multiplier=LINK_SHARE_DEVALUE_MULTIPLIER)
    return LinkShareClassification(is_bare_link_share=False)


def classify(source: str, raw_json: dict, text: str) -> LinkShareClassification:
    """Whether a post is a "bare link-share" -- a link with no real take of
    its own -- and, if so, the base_score multiplier to apply. Three shapes
    count: the author's own words (URLs/hashtags stripped) are empty or a
    verbatim substring of the link card's title; they're a near-subset of
    the title's words (LINK_SHARE_TITLE_OVERLAP_RATIO); or there's no card
    at all but a link plus a short hashtag-bag caption
    (LINK_SHARE_THIN_CAPTION_CHARS / LINK_SHARE_HASHTAG_BAG_RATIO). A post
    with a real sentence of its own (over LINK_SHARE_MAX_ORIGINAL_CHARS) is
    always unaffected."""
    stripped = _strip(text)
    if len(stripped) > LINK_SHARE_MAX_ORIGINAL_CHARS:
        return _bare(False)

    # Card-independent: a link + a short hashtag-bag caption.
    if (
        _URL_RE.search(text or "")
        and len(stripped) <= LINK_SHARE_THIN_CAPTION_CHARS
        and _hashtag_ratio(text) >= LINK_SHARE_HASHTAG_BAG_RATIO
    ):
        return _bare(True)

    title = _card_title(source, raw_json)
    if title is None:
        return _bare(False)

    normalized_title = _WHITESPACE_RE.sub(" ", title).strip().casefold()
    # Empty stripped text (just a URL and/or hashtags) is the purest bare
    # share; then the verbatim-substring check; then the fuzzy word-overlap
    # fallback for a restated headline with trailing decoration.
    if stripped == "" or stripped in normalized_title:
        return _bare(True)
    return _bare(_title_overlap(stripped, normalized_title) >= LINK_SHARE_TITLE_OVERLAP_RATIO)
