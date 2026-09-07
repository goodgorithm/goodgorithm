"""Down-weights a "now playing on <station>" radio/stream post that isn't
already excluded by the bot filter -- a station account's first post of a
cycle (before bot_filter.nowplaying_shape's repeat count crosses its
threshold), or a low-volume station that never crosses it. Enthusiastic
station boilerplate scores well on sentiment and clears the topicality
floor, so without this one such post per station rides to the top of the
feed each cycle. Not off-mission enough to hard-exclude -- a person's own
"now playing on <community station>" is a real post -- so this is a
base_score devalue multiplier, the same category as context_dependency.py /
link_share.py / aggregator_demote.py.

Gated purely on bot_filter.nowplaying_shape() -- the structured
"now playing on <station>" / "Artist: ... Title: ..." forms, never a bare
"#nowplaying" tag or a person naming a track they like -- so it composes
with the bot filter: a repeating station is already is_bot and never
ranked, and this only bites on the shape that survives.
"""

import os
from dataclasses import dataclass

from pipeline_stages import bot_filter

# base_score multiplier for a now-playing-shaped post -- same default as
# aggregator_demote.py's, reflecting that these carry no original content
# either. See the wiki's Ranking page. Treat any non-default value as
# unvalidated against real production data.
NOWPLAYING_DEMOTE_MULTIPLIER = float(os.environ.get("NOWPLAYING_DEMOTE_MULTIPLIER", "0.3"))
if not 0.0 < NOWPLAYING_DEMOTE_MULTIPLIER <= 1.0:
    raise ValueError(
        f"NOWPLAYING_DEMOTE_MULTIPLIER ({NOWPLAYING_DEMOTE_MULTIPLIER}) must be in (0.0, 1.0]"
    )


@dataclass(frozen=True)
class NowPlayingClassification:
    is_nowplaying: bool
    devalue_multiplier: float = 1.0  # base_score multiplier; 1.0 == no penalty


def classify(text: str) -> NowPlayingClassification:
    """Whether a post is a structured now-playing / radio-bot post and, if
    so, the base_score multiplier to apply. A bare "#nowplaying" tag, a
    "tune in" / "streaming live" post, or a person naming a track is
    unaffected."""
    if bot_filter.nowplaying_shape(text) is not None:
        return NowPlayingClassification(is_nowplaying=True, devalue_multiplier=NOWPLAYING_DEMOTE_MULTIPLIER)
    return NowPlayingClassification(is_nowplaying=False)
