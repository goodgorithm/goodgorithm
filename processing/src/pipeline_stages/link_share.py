"""Down-weights a "bare link-share" in ranking: a post carrying a link
card whose own text adds nothing beyond the card's own title -- a
WordPress/Buffer/dlvr.it/RSS auto-crosspost, or a manual "here's a link"
with no take of its own. Low-value in the feed but not bad content (some
are genuine must-read reshares), so this produces a base_score
devaluation, not a hard exclude like content_filter/context_dependency.
See the wiki's Ranking page.

There's no structural "this is a link-share" marker on either platform --
Mastodon's card.type is "link" for a personal blog, a news story and a
YouTube video alike. The only signal is behavioral: a link card is
present and the author's own words (URLs and hashtags stripped) are a
substring of the card title.
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
# never devalue regardless of the substring match.
LINK_SHARE_MAX_ORIGINAL_CHARS = int(os.environ.get("LINK_SHARE_MAX_ORIGINAL_CHARS", "200"))

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


def classify(source: str, raw_json: dict, text: str) -> LinkShareClassification:
    """Whether a post is a bare link-share (link card present, own text adds
    nothing beyond the card title) and, if so, the base_score multiplier to
    apply. A post with no link card, or one whose own text isn't contained
    in the card title, is unaffected."""
    title = _card_title(source, raw_json)
    if title is None:
        return LinkShareClassification(is_bare_link_share=False)

    stripped = _strip(text)
    if len(stripped) > LINK_SHARE_MAX_ORIGINAL_CHARS:
        return LinkShareClassification(is_bare_link_share=False)

    normalized_title = _WHITESPACE_RE.sub(" ", title).strip().casefold()
    # Empty stripped text (just a URL and/or hashtags) is the purest bare
    # share; otherwise the author's whole remaining text has to appear
    # verbatim inside the card title.
    if stripped == "" or stripped in normalized_title:
        return LinkShareClassification(
            is_bare_link_share=True, devalue_multiplier=LINK_SHARE_DEVALUE_MULTIPLIER
        )
    return LinkShareClassification(is_bare_link_share=False)
