from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Bumped whenever the underlying scoring method changes (e.g. swapping in
# the trained CNN) — stored alongside every score so old and new results
# are distinguishable in processed_posts.
SENTIMENT_METHOD = "vader_v1"

_analyzer: SentimentIntensityAnalyzer | None = None


def _get_analyzer() -> SentimentIntensityAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def score_sentiment(text: str) -> float:
    """Placeholder sentiment scorer, [-1, 1]. This is the entire contract
    the rest of the pipeline depends on — the future trained CNN (loaded
    from R2, CPU inference) swaps in by rewriting only this function's
    internals and bumping SENTIMENT_METHOD; nothing upstream or downstream
    changes."""
    return _get_analyzer().polarity_scores(text)["compound"]
