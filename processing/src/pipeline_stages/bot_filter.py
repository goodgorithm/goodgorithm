import hashlib
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from infra import redis_client
from text_normalize import normalize_text

VELOCITY_WINDOW_SECONDS = 60 * 60  # 1 hour
VELOCITY_THRESHOLD = 15  # posts/hour at which the velocity component maxes out
SELF_DUP_TTL_SECONDS = 24 * 60 * 60  # matches dedup's cluster-membership TTL

URL_DENSITY_CAP = 0.3
HASHTAG_DENSITY_CAP = 0.4
CAPS_RATIO_CAP = 0.6

# Skeleton window: first TEMPLATE_PREFIX_WORDS + last TEMPLATE_SUFFIX_WORDS
# words of the normalized text. See the wiki's Pipeline Internals page
# (bot filter's Template repetition section) for why these specific
# widths, and why cross-account skeleton collisions aren't a risk.
TEMPLATE_PREFIX_WORDS = 3
TEMPLATE_SUFFIX_WORDS = 2
# Rolling window like self-dup's TTL, not velocity's -- see the wiki.
TEMPLATE_REPEAT_TTL_SECONDS = SELF_DUP_TTL_SECONDS
TEMPLATE_REPEAT_THRESHOLD = 5  # same-skeleton repeats from one author before this maxes out

VELOCITY_WEIGHT = 0.30
SELF_DUP_WEIGHT = 0.25
LEXICAL_WEIGHT = 0.20
TEMPLATE_WEIGHT = 0.25
BOT_SCORE_THRESHOLD = 0.5

# Also matches bare www.-prefixed links with no scheme, not just
# http(s)://. Deliberately not extended to fully bare domains with
# neither prefix (e.g. "amazon.com/xyz") -- that needs a TLD allowlist to
# avoid false positives on ordinary prose ("e.g.", "Mr. Smith"), a
# separate, larger piece of work.
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
    TEMPLATE_SUFFIX_WORDS words of the normalized text. Catches a fixed
    template wrapped around long variable content (e.g. "Now playing on
    X: SONG by ARTIST! Tune in now: URL") that dedup.py's whole-text
    MinHash/Jaccard is blind to, since a short fixed template diluted by
    a long variable middle never crosses JACCARD_THRESHOLD. See the
    wiki's Pipeline Internals page."""
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
    durable is_bot/bot_score result. Each method batches its read/write
    pair into one pipelined round trip rather than issuing them
    separately -- see the wiki's Pipeline Internals page."""

    def __init__(self) -> None:
        self.client = redis_client.get_client()

    def bump_velocity(self, author_id: str) -> int:
        key = f"botvel:{author_id}"
        pipe = self.client.pipeline()
        pipe.incr(key)
        # nx=True: only sets a fresh TTL on this key's first write in the
        # window, so the window is fixed (resets exactly
        # VELOCITY_WINDOW_SECONDS after the first post) rather than
        # extending with continued activity.
        pipe.expire(key, VELOCITY_WINDOW_SECONDS, nx=True)
        results = pipe.exec()
        return results[0]

    def check_and_record_self_duplicate(self, author_id: str, cluster_id: str) -> bool:
        key = f"cluster:{cluster_id}:authors"
        pipe = self.client.pipeline()
        pipe.sadd(key, author_id)
        # nx=True -- this set grows with each new author, so without it a
        # sustained bot wave (many distinct authors reposting into one
        # cluster, exactly what this check exists to catch) could keep
        # pushing the TTL forward on every new member, growing the set
        # unbounded instead of clearing on a fixed window. See the wiki's
        # Pipeline Internals page.
        pipe.expire(key, SELF_DUP_TTL_SECONDS, nx=True)
        results = pipe.exec()
        added = results[0]
        return added == 0  # already a member => this author already posted into this cluster

    def bump_template_repeat(self, author_id: str, skeleton: str) -> int:
        # Hashed, not raw skeleton text, in the key -- bounded key length,
        # same reasoning as dedup.py's band_hashes and topicality.py's
        # ENTITY_KEY_MAX_LEN.
        digest = hashlib.sha1(skeleton.encode("utf8")).hexdigest()
        key = f"tmpl:{author_id}:{digest}"
        pipe = self.client.pipeline()
        pipe.incr(key)
        # Rolling TTL, refreshed on every hit -- deliberately not the
        # NX-only-on-first-hit pattern the two methods above use. See the
        # wiki's Pipeline Internals page for why this key needs the
        # opposite TTL shape.
        pipe.expire(key, TEMPLATE_REPEAT_TTL_SECONDS)
        results = pipe.exec()
        return results[0]


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
    template repetition. Never reads likes/reposts/replies/follower
    counts. Defensive-only: this produces a filter flag, never a ranking
    boost. See the wiki's Pipeline Internals page."""
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
