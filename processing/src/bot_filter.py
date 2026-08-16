import hashlib
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import redis_client
from text_normalize import normalize_text

VELOCITY_WINDOW_SECONDS = 60 * 60  # 1 hour
VELOCITY_THRESHOLD = 15  # posts/hour at which the velocity component maxes out
SELF_DUP_TTL_SECONDS = 24 * 60 * 60  # matches dedup's cluster-membership TTL

URL_DENSITY_CAP = 0.3
HASHTAG_DENSITY_CAP = 0.4
CAPS_RATIO_CAP = 0.6

# How many words of the normalized text form the "skeleton" checked for
# repetition (issue #40) -- long enough to be a real fixed template, short
# enough to reliably land inside it rather than spilling into variable
# content. Originally 4-word-prefix + 3-word-suffix, validated against
# "Now playing on Mixify Evergreen Hits: SONG! Tune in now: URL" vs
# "...Mixify Bangla Hits: SONG! Tune in now: URL" (identical skeleton
# despite whole-text Jaccard of ~0.01-0.13 between them -- see dedup.py's
# JACCARD_THRESHOLD=0.7, nowhere close).
#
# Narrowed to 3+2 after a real production account ("Joint Radio",
# jointil@mastodon.social) evaded that window: it rotates across several
# named "stations" ("Joint Radio Beat Trance", "...Reggae", "...Blues
# Rock"), each with its own emoji landing exactly on word 4 and its own
# genre hashtag landing in the last 3 words -- e.g. "Now playing on 🎧
# Joint Radio Beat Trance: ... #PsyTrance #NowPlaying #Radio" vs "Now
# playing on ❤️💛💚 Joint Radio Reggae: ... #Rocksteady #NowPlaying
# #Radio". Each station computed to a different skeleton, splitting one
# account's repeat count across several counters instead of accumulating
# in one. Confirmed directly against the real text that 3-word-prefix
# ("now playing on") + 2-word-suffix ("#nowplaying #radio") is common
# across all of that account's stations. Different accounts sharing an
# otherwise-similar skeleton under the narrower window (e.g. Mixify and
# DFM both reducing to "now playing on || in now:") is fine, not a
# regression -- bump_template_repeat is keyed by (author_id, skeleton),
# so cross-account collisions were never a correctness risk.
TEMPLATE_PREFIX_WORDS = 3
TEMPLATE_SUFFIX_WORDS = 2
# Same 24h window as SELF_DUP_TTL_SECONDS, not VELOCITY_WINDOW_SECONDS --
# a lower-volume templated bot may take longer than an hour to accumulate
# enough repeats to be conclusive; this is "structural repetition over
# time", closer in spirit to self-duplication than to short-window velocity.
TEMPLATE_REPEAT_TTL_SECONDS = SELF_DUP_TTL_SECONDS
TEMPLATE_REPEAT_THRESHOLD = 5  # same-skeleton repeats from one author before this maxes out

VELOCITY_WEIGHT = 0.30
SELF_DUP_WEIGHT = 0.25
LEXICAL_WEIGHT = 0.20
TEMPLATE_WEIGHT = 0.25
BOT_SCORE_THRESHOLD = 0.5

# Also matches bare www.-prefixed links with no scheme (confirmed 2026-08-11:
# a promotional post's 4 Amazon links, written as "www.amazon.com/dp/..."
# with no "http(s)://", scored zero url_density and slipped through this
# filter). Deliberately not extended to fully bare domains with neither
# prefix (e.g. "amazon.com/xyz") -- that needs a TLD allowlist to avoid
# false positives on ordinary prose ("e.g.", "Mr. Smith"), a separate,
# larger fix.
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_HASHTAG_RE = re.compile(r"#\w+")


def url_density(text: str) -> float:
    words = text.split()
    if not words:
        return 0.0
    return len(_URL_RE.findall(text)) / len(words)


def hashtag_density(text: str) -> float:
    words = text.split()
    if not words:
        return 0.0
    return len(_HASHTAG_RE.findall(text)) / len(words)


def caps_ratio(text: str) -> float:
    # words of len >= 3 only, so acronyms like "US"/"AI" don't skew this
    words = [w for w in text.split() if len(w) >= 3 and w.isalpha()]
    if not words:
        return 0.0
    return sum(1 for w in words if w.isupper()) / len(words)


def lexical_score(text: str) -> float:
    """Any single strong spam signal (link-stuffing, hashtag-stuffing, or
    shouting) is enough on its own — so this takes the max of the three
    normalized components rather than averaging, which would dilute a
    post that's clean except for one loud signal."""
    url_component = min(1.0, url_density(text) / URL_DENSITY_CAP)
    hashtag_component = min(1.0, hashtag_density(text) / HASHTAG_DENSITY_CAP)
    caps_component = min(1.0, caps_ratio(text) / CAPS_RATIO_CAP)
    return max(url_component, hashtag_component, caps_component)


def template_skeleton(text: str) -> str:
    """A structural fingerprint -- the first TEMPLATE_PREFIX_WORDS and last
    TEMPLATE_SUFFIX_WORDS words of the normalized text (issue #40). Catches
    a fixed template wrapped around long variable content (e.g. "Now
    playing on X: SONG by ARTIST! Tune in now: URL") that dedup.py's
    whole-text MinHash/Jaccard is blind to, since a short fixed template
    diluted by a long variable middle never crosses JACCARD_THRESHOLD."""
    words = normalize_text(text).split()
    prefix = words[:TEMPLATE_PREFIX_WORDS]
    suffix = words[-TEMPLATE_SUFFIX_WORDS:] if len(words) > TEMPLATE_PREFIX_WORDS else []
    return "|".join(prefix) + "||" + "|".join(suffix)


class BotFilterIndex(Protocol):
    def bump_velocity(self, author_id: str) -> int: ...
    def check_and_record_self_duplicate(self, author_id: str, cluster_id: str) -> bool: ...
    def bump_template_repeat(self, author_id: str, skeleton: str) -> int: ...


class RedisBotFilterIndex:
    """Per-author posting velocity and self-duplication state, in Upstash
    Redis. Ephemeral/TTL'd, like dedup's LSH state — Postgres holds the
    durable is_bot/bot_score result."""

    def __init__(self) -> None:
        self.client = redis_client.get_client()

    def bump_velocity(self, author_id: str) -> int:
        key = f"botvel:{author_id}"
        count = self.client.incr(key)
        if count == 1:
            # only the author's first post in the window needs a fresh TTL --
            # skipping it on every later post also cuts a full Redis command
            # per repeat post, which matters at volume. Trade-off: the window
            # is now fixed (resets exactly VELOCITY_WINDOW_SECONDS after the
            # first post) rather than extending with continued activity.
            self.client.expire(key, VELOCITY_WINDOW_SECONDS)
        return count

    def check_and_record_self_duplicate(self, author_id: str, cluster_id: str) -> bool:
        key = f"cluster:{cluster_id}:authors"
        added = self.client.sadd(key, author_id)
        if added:
            # only call expire when a genuinely new author joins the cluster --
            # repeat-duplicate confirmations (added == 0) don't need it, and
            # that's exactly the call pattern that fires most during a real
            # spam burst, so this is where the savings concentrate. nx=True:
            # only the *first* new author actually sets the TTL -- without
            # it, a sustained bot wave (many distinct authors reposting into
            # one cluster, exactly what this filter exists to catch) pushed
            # the 24h TTL forward on every new author and could keep this set
            # growing unbounded, indefinitely (2026-08-12 incident).
            self.client.expire(key, SELF_DUP_TTL_SECONDS, nx=True)
        return added == 0  # already a member => this author already posted into this cluster

    def bump_template_repeat(self, author_id: str, skeleton: str) -> int:
        # Hashed, not raw skeleton text, in the key -- same reasoning as
        # dedup.py's band_hashes (bounded key length) and topicality.py's
        # ENTITY_KEY_MAX_LEN (unbounded-length keys are a real risk here,
        # not hypothetical -- see the 2026-08-12 Redis capacity incident).
        digest = hashlib.sha1(skeleton.encode("utf8")).hexdigest()
        key = f"tmpl:{author_id}:{digest}"
        count = self.client.incr(key)
        # Rolling TTL, refreshed on every hit -- deliberately NOT the
        # NX-only-on-first-hit pattern bump_velocity/
        # check_and_record_self_duplicate use. Confirmed live (issue #40
        # follow-up, 2026-08-16): with a fixed NX-only TTL, several
        # genuinely continuous bots' counters all expired exactly 24h
        # after the fix's first post-deploy hit and silently reset to
        # zero, letting Mixify/DFM/QWRT/Radio Digital Malayali/Joint Radio
        # all slip back under BOT_SCORE_THRESHOLD simultaneously -- not a
        # new evasion, the same accounts cycling through a "ramping back
        # up" phase on a 24h clock, forever. This key is a single
        # fixed-size integer counter, not a growing SET like
        # cluster:*:authors (the 2026-08-12 incident that motivated NX
        # there) -- refreshing its own TTL doesn't risk unbounded memory
        # growth, and "has this author established a durable pattern"
        # should persist as long as the behavior continues, only decaying
        # once they've genuinely stopped for a full day.
        self.client.expire(key, TEMPLATE_REPEAT_TTL_SECONDS)
        return count


@dataclass
class BotScore:
    bot_score: float
    is_bot: bool
    velocity_component: float
    self_dup_component: float
    lexical_component: float
    template_component: float


def score_bot(author_id: str, text: str, cluster_id: UUID, index: BotFilterIndex) -> BotScore:
    """Content-derived bot heuristics only — posting velocity, self-repost
    rate (via dedup cluster membership), lexical spam patterns, and
    template repetition (issue #40). Never reads likes/reposts/replies/
    follower counts. Defensive-only: this produces a filter flag, never a
    ranking boost."""
    velocity_count = index.bump_velocity(author_id)
    velocity_component = min(1.0, velocity_count / VELOCITY_THRESHOLD)

    is_self_dup = index.check_and_record_self_duplicate(author_id, str(cluster_id))
    self_dup_component = 1.0 if is_self_dup else 0.0

    lex_component = lexical_score(text)

    template_count = index.bump_template_repeat(author_id, template_skeleton(text))
    template_component = min(1.0, template_count / TEMPLATE_REPEAT_THRESHOLD)

    bot_score = (
        VELOCITY_WEIGHT * velocity_component
        + SELF_DUP_WEIGHT * self_dup_component
        + LEXICAL_WEIGHT * lex_component
        + TEMPLATE_WEIGHT * template_component
    )

    return BotScore(
        bot_score=bot_score,
        is_bot=bot_score >= BOT_SCORE_THRESHOLD,
        velocity_component=velocity_component,
        self_dup_component=self_dup_component,
        lexical_component=lex_component,
        template_component=template_component,
    )
