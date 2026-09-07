"""Registry of "post shapes" -- named, structured, largely-automated post
patterns that earn a base_score devalue and, optionally, feed the bot
filter's repeat-gated is_bot override. "now playing on <station>" radio/
stream bots are the first entry; flight-tracker bots, affiliate/counterfeit
spam and campaign-donation keyword posts are the same kind of gap (see the
wiki's Content Policy page).

One registry, structured like context_dependency.py's PLATFORM_POLICIES --
adding a shape means one SHAPES entry plus its true/false-positive fixture
corpus, nothing else changes. Each shape's `match` returns a stable
per-entity grouping key (a radio station, say) so an automated account's
posts accumulate under one key in the bot filter's repeat counter, or None.

The regex patterns live here in code, never the DB: processing/ is one
long-lived loop, stdlib `re` has no timeout and there's no linear-time
engine available, so a catastrophic-backtracking pattern from the DB would
hang the whole pipeline with no mitigation. The `post_shapes` DB table
carries only the operational knobs (enabled / devalue_multiplier /
repeat_threshold), overriding the code defaults below -- see
db.fetch_post_shape_config and the wiki's Configuration page.
"""

import re
from dataclasses import dataclass
from typing import Callable, Protocol

# --- "nowplaying" shape ------------------------------------------------------

# "now playing on <station>" and its close variants. Anchored on the opener
# so a bare "#nowplaying" tag, "tune in" / "streaming live" (podcast and
# Twitch self-promo), and a person sharing what they're listening to
# ("Just liked ...") don't match -- only a station/stream announcing a track.
_NOWPLAYING_ON_RE = re.compile(
    r"(?:^|[\s>\"'“])(?:#?\s?now\s?playing|now\s+on\s+air|live\s+now)\s+on\s+(?P<station>[^\n:!(]*)",
    re.IGNORECASE,
)
_NOWPLAYING_NOW_ON_RE = re.compile(
    r"(?:^|[\s>\"'“])now\s+on\s+(?P<station>[^\n:!(]*?):",
    re.IGNORECASE,
)
# The BBC family's link-free "<BBC Radio N ...show...> Now Playing <artist>
# <track>" shape, which carries no "on <station>".
_NOWPLAYING_BBC_RE = re.compile(
    r"^bbc\s+(?:radio|asian|introducing|world|sounds|music)\b.*?\bnow\s+playing\b",
    re.IGNORECASE | re.DOTALL,
)
# The tibr*/tibtv* federated Mastodon bot's structured block.
_NOWPLAYING_STRUCTURED_RE = re.compile(r"\bartist:\s*\S.*?\btitle:\s*\S", re.IGNORECASE | re.DOTALL)
_NOWPLAYING_STATION_FIELD_RE = re.compile(r"\b(?:station|show):\s*\"?([^\"\n]+)", re.IGNORECASE)
_NOWPLAYING_KEY_CLEAN_RE = re.compile(r"[^a-z0-9]+")


def _nowplaying_key(station: str) -> str:
    """A station identifier reduced to its first few ASCII words -- drops
    leading emoji/decoration and the per-track tail, so every post from one
    station collapses to the same key."""
    ascii_only = station.encode("ascii", "ignore").decode("ascii")
    words = ascii_only.split()[:3]
    return _NOWPLAYING_KEY_CLEAN_RE.sub("-", " ".join(words).lower()).strip("-")


def _nowplaying_match(text: str) -> str | None:
    """A stable per-station key when `text` is a structured "now playing on
    <station>" / radio-bot post -- the shape a station account emits many
    times a day with only the track, artist and hashtags changing -- else
    None. A bare "#nowplaying" tag, "tune in" / "streaming live", and a
    person naming a track they like all return None."""
    if not text:
        return None
    for pattern in (_NOWPLAYING_ON_RE, _NOWPLAYING_NOW_ON_RE):
        match = pattern.search(text)
        if match:
            return _nowplaying_key(match.group("station")) or "x"
    if _NOWPLAYING_BBC_RE.search(text):
        return _nowplaying_key(text) or "bbc"
    if _NOWPLAYING_STRUCTURED_RE.search(text):
        field = _NOWPLAYING_STATION_FIELD_RE.search(text)
        return (_nowplaying_key(field.group(1)) if field else "") or "structured"
    return None


# --- registry --------------------------------------------------------------


@dataclass(frozen=True)
class PostShape:
    name: str  # lowercase slug; the `post_shapes` DB row is keyed by this
    match: Callable[[str], str | None]  # -> per-entity grouping key, or None
    devalue_multiplier: float  # code default; a post_shapes row overrides it
    repeat_threshold: int | None  # None -> devalue only, no is_bot override


SHAPES: tuple[PostShape, ...] = (
    PostShape(name="nowplaying", match=_nowplaying_match, devalue_multiplier=0.3, repeat_threshold=3),
)


class ShapeConfig(Protocol):
    """The per-shape knobs a `post_shapes` DB row carries (db.PostShapeConfig
    satisfies this structurally). A row fully specifies a shape's knobs; a
    shape with no row falls back to its PostShape registry literals."""

    enabled: bool
    devalue_multiplier: float
    repeat_threshold: int | None


@dataclass(frozen=True)
class ShapeMatch:
    name: str
    key: str  # the shape's per-entity grouping key ("" if the shape has no sub-key)
    devalue_multiplier: float
    repeat_threshold: int | None


def classify(text: str, shape_config: dict[str, ShapeConfig] | None = None) -> ShapeMatch | None:
    """The first registered shape `text` matches, with its grouping key and
    its effective knobs (a `post_shapes` row overrides the registry
    literals; a disabled shape is skipped). None if nothing matches."""
    for shape in SHAPES:
        cfg = (shape_config or {}).get(shape.name)
        if cfg is not None and not cfg.enabled:
            continue
        key = shape.match(text)
        if key is None:
            continue
        if cfg is not None:
            return ShapeMatch(shape.name, key, cfg.devalue_multiplier, cfg.repeat_threshold)
        return ShapeMatch(shape.name, key, shape.devalue_multiplier, shape.repeat_threshold)
    return None
