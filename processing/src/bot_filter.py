import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import redis_client

VELOCITY_WINDOW_SECONDS = 60 * 60  # 1 hour
VELOCITY_THRESHOLD = 15  # posts/hour at which the velocity component maxes out
SELF_DUP_TTL_SECONDS = 14 * 24 * 60 * 60  # matches dedup's cluster-membership TTL

URL_DENSITY_CAP = 0.3
HASHTAG_DENSITY_CAP = 0.4
CAPS_RATIO_CAP = 0.6

VELOCITY_WEIGHT = 0.40
SELF_DUP_WEIGHT = 0.35
LEXICAL_WEIGHT = 0.25
BOT_SCORE_THRESHOLD = 0.5

_URL_RE = re.compile(r"https?://\S+")
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


class BotFilterIndex(Protocol):
    def bump_velocity(self, author_id: str) -> int: ...
    def check_and_record_self_duplicate(self, author_id: str, cluster_id: str) -> bool: ...


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
            # only refresh TTL when a genuinely new author joins the cluster --
            # repeat-duplicate confirmations (added == 0) don't need it, and
            # that's exactly the call pattern that fires most during a real
            # spam burst, so this is where the savings concentrate.
            self.client.expire(key, SELF_DUP_TTL_SECONDS)
        return added == 0  # already a member => this author already posted into this cluster


@dataclass
class BotScore:
    bot_score: float
    is_bot: bool
    velocity_component: float
    self_dup_component: float
    lexical_component: float


def score_bot(author_id: str, text: str, cluster_id: UUID, index: BotFilterIndex) -> BotScore:
    """Content-derived bot heuristics only — posting velocity, self-repost
    rate (via dedup cluster membership), and lexical spam patterns. Never
    reads likes/reposts/replies/follower counts. Defensive-only: this
    produces a filter flag, never a ranking boost."""
    velocity_count = index.bump_velocity(author_id)
    velocity_component = min(1.0, velocity_count / VELOCITY_THRESHOLD)

    is_self_dup = index.check_and_record_self_duplicate(author_id, str(cluster_id))
    self_dup_component = 1.0 if is_self_dup else 0.0

    lex_component = lexical_score(text)

    bot_score = (
        VELOCITY_WEIGHT * velocity_component
        + SELF_DUP_WEIGHT * self_dup_component
        + LEXICAL_WEIGHT * lex_component
    )

    return BotScore(
        bot_score=bot_score,
        is_bot=bot_score >= BOT_SCORE_THRESHOLD,
        velocity_component=velocity_component,
        self_dup_component=self_dup_component,
        lexical_component=lex_component,
    )
