"""The political-content hard-exclude -- a product-policy exclude, distinct
from every check in content_filter.py: those are all moderation-derived
(hashtag self-labels, sensitive media, suppressed domains); this one is a
topic-based product decision, triggered only when the trained classifier and
the independent nearest-centroid signal both agree a post is political. Kept
in its own module rather than folded into content_filter.py for that reason.
"""

import os

# Both signals must independently clear their threshold before a post is
# excluded -- excluding is irreversible and invisible to the user, so this
# uses the stricter, higher-precision operating point (99.2% precision /
# ~32% recall on the held-out political/civic-tone evaluation set).
POLITICAL_EXCLUDE_CLASSIFIER_THRESHOLD = float(
    os.environ.get("POLITICAL_EXCLUDE_CLASSIFIER_THRESHOLD", "0.7128")
)
POLITICAL_EXCLUDE_CENTROID_THRESHOLD = float(os.environ.get("POLITICAL_EXCLUDE_CENTROID_THRESHOLD", "0.0058"))


def is_political_excluded(classifier_score: float | None, centroid_score: float | None) -> bool:
    """True only when both signals are available and both clear their
    threshold. A missing signal (model not loaded) never excludes on its
    own -- fail-open, same discipline as every other model-backed stage."""
    if classifier_score is None or centroid_score is None:
        return False
    return (
        classifier_score >= POLITICAL_EXCLUDE_CLASSIFIER_THRESHOLD
        and centroid_score >= POLITICAL_EXCLUDE_CENTROID_THRESHOLD
    )
