"""Down-weights a "hashtag bag": a post that is mostly a pile of hashtags
with little or no prose of its own -- `#GrandCanyon #Arizona #Sunset
#Orange #Trees #Beautiful`, a 14-tag author self-promo run, a
`#LifeCoach #RelationshipCoach #RelationshipAdvice ...` discoverability
spray. The hashtag words carry enthusiastic-sounding vocabulary, so
surface-valence sentiment rates the post positive and it clears the
topicality floor, but there is no actual content -- it ranks on keyword
soup. Not off-mission enough to hard-exclude (some are an artist tagging
a genuine piece of work), so this is a `base_score` devalue multiplier,
the same category as `context_dependency.py` / `link_share.py` /
`aggregator_demote.py`.

Deliberately narrow -- it only fires on the pile-of-tags shape, not on
"short + positive" in general (a real "New Kirby? Looks cute!" has no
hashtags and is untouched). A post carrying a link is left to
`link_share.py`, which devalues a link + hashtag-bag caption; this one is
the no-link case. See the wiki's Ranking / Content Policy pages.
"""

import os
import re
from dataclasses import dataclass

# base_score multiplier for a hashtag bag -- milder than
# aggregator_demote's 0.3, since a hashtag bag isn't automated
# syndication, just a low-effort human post that the ranker over-weights.
# See the wiki's Ranking page. Treat any non-default value as unvalidated
# against real production data.
HASHTAG_BAG_DEVALUE_MULTIPLIER = float(os.environ.get("HASHTAG_BAG_DEVALUE_MULTIPLIER", "0.5"))
if not 0.0 < HASHTAG_BAG_DEVALUE_MULTIPLIER <= 1.0:
    raise ValueError(
        f"HASHTAG_BAG_DEVALUE_MULTIPLIER ({HASHTAG_BAG_DEVALUE_MULTIPLIER}) must be in (0.0, 1.0]"
    )

# The most prose words (hashtags/mentions/URLs/emoji/punctuation stripped)
# a post can carry and still count as a bag. At 3, "Just having fun #a #b
# #c #d" is a bag but "Beautiful shot today, the light was unreal #a #b
# #c" (7 prose words) is a real caption and untouched.
HASHTAG_BAG_MAX_PROSE_WORDS = int(os.environ.get("HASHTAG_BAG_MAX_PROSE_WORDS", "3"))

# The fewest hashtags required. Two topic tags on a short post is normal
# use; three-plus with almost no prose is the bag shape.
HASHTAG_BAG_MIN_HASHTAGS = int(os.environ.get("HASHTAG_BAG_MIN_HASHTAGS", "3"))

_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_HASHTAG_RE = re.compile(r"#\w+")
_MENTION_RE = re.compile(r"@[\w.-]+")
_NON_WORD_RE = re.compile(r"[^\w\s]")  # \w is Unicode-aware -> drops emoji/punct, keeps any-script letters


@dataclass(frozen=True)
class HashtagBagClassification:
    is_hashtag_bag: bool
    devalue_multiplier: float = 1.0  # base_score multiplier; 1.0 == no penalty


def _prose_word_count(text: str) -> int:
    """Words left after removing URLs, hashtags (entirely -- not expanded
    the way util/text_normalize does), mentions, then emoji/punctuation."""
    stripped = _URL_RE.sub(" ", text)
    stripped = _HASHTAG_RE.sub(" ", stripped)
    stripped = _MENTION_RE.sub(" ", stripped)
    stripped = _NON_WORD_RE.sub(" ", stripped)
    return len(stripped.split())


def classify(text: str) -> HashtagBagClassification:
    """Whether a post is a hashtag bag and, if so, the base_score
    multiplier to apply. Fires only when the post carries no link, has at
    least HASHTAG_BAG_MIN_HASHTAGS hashtags, has at most
    HASHTAG_BAG_MAX_PROSE_WORDS words of its own, and the hashtags
    outnumber those words."""
    text = text or ""
    if _URL_RE.search(text):
        return HashtagBagClassification(is_hashtag_bag=False)

    hashtag_count = len(_HASHTAG_RE.findall(text))
    if hashtag_count < HASHTAG_BAG_MIN_HASHTAGS:
        return HashtagBagClassification(is_hashtag_bag=False)

    prose_words = _prose_word_count(text)
    if prose_words <= HASHTAG_BAG_MAX_PROSE_WORDS and hashtag_count > prose_words:
        return HashtagBagClassification(
            is_hashtag_bag=True, devalue_multiplier=HASHTAG_BAG_DEVALUE_MULTIPLIER
        )
    return HashtagBagClassification(is_hashtag_bag=False)
