"""The quality hard-exclude -- unlike political_exclude.py's AND-gate (two
independent signals must both clear their own threshold), this is a
single-signal threshold: #242 found no structural combination (AND-gate
paired with any other available signal, majority-vote ensemble, unanimous
AND) beat this classifier alone at matched volume, so there's no second
signal worth pairing it with.
"""

import os

# The decided deployment threshold -- a good-retention-floor-constrained
# measurement (#238's threshold-selection findings), not an unconstrained
# "best separation" point. Re-derived (not re-decided ad hoc) on every
# training run going forward -- see the release-quality-classifier skill.
QUALITY_EXCLUDE_THRESHOLD = float(os.environ.get("QUALITY_EXCLUDE_THRESHOLD", "0.39"))


def is_quality_excluded(quality_score: float | None) -> bool:
    """True only when a score is available and it sits below the
    threshold. A missing signal (model not loaded) never excludes on its
    own -- fail-open, same discipline as every other model-backed stage."""
    if quality_score is None:
        return False
    return quality_score < QUALITY_EXCLUDE_THRESHOLD
