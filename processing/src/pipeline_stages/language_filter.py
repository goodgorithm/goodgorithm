import logging
import tempfile
from pathlib import Path

import fasttext
import requests

logger = logging.getLogger("processing")

# Meta's official pretrained language-ID model (176 languages, trained on
# Wikipedia/Tatoeba/SETimes) -- confirmed against real production text
# before choosing it over lingua-py (issue #28: benchmarked both against
# 400 real lang='en' posts and a hand-verified 32-post multilingual set --
# fastText had roughly half lingua-py's false-positive rate on real
# English, 5.0% vs 9.0%, with identical 100% recall on confirmed
# non-English text, and a ~175x smaller footprint). Fetched at runtime
# rather than committed to the repo -- this project's .gitignore already
# states "ML artifacts... are large and versioned separately, not in
# git" -- the same fetch-a-pinned-third-party-artifact shape
# pyproject.toml already uses for en_core_web_sm's wheel URL. Meta's own
# CDN has hosted this exact file at this exact URL for years, same
# reliability bar as a GitHub Releases URL.
MODEL_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz"
MODEL_PATH = Path(tempfile.gettempdir()) / "lid.176.ftz"
FETCH_TIMEOUT_SECONDS = 30

# Tuned against real production text (issue #28): the lowest threshold
# where fastText's false-positive rate on confirmed-English posts drops
# meaningfully (5.0% -> 3.5%) while recall on confirmed non-English text
# stays perfect (32/32). Below this, low-confidence guesses on short or
# ambiguous text (a handful of words, an emoji, a bare URL) dominate the
# false-positive rate for no real gain; above ~0.5 recall starts dropping
# faster than the false-positive rate improves.
CONFIDENCE_THRESHOLD = 0.3

_model: fasttext.FastText._FastText | None = None
_load_failed = False


def _get_model() -> fasttext.FastText._FastText | None:
    """None if the model couldn't be loaded -- tried once per process,
    same "best-effort, degrade gracefully rather than crash" shape as
    sentiment.py's CNN-load-falls-back-to-VADER pattern (this hard-exclude
    gate just becomes a no-op instead, per is_non_english's None handling
    below, rather than taking the whole cycle down)."""
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    try:
        if not MODEL_PATH.exists():
            logger.info("fetching language-ID model from %s", MODEL_URL)
            response = requests.get(MODEL_URL, timeout=FETCH_TIMEOUT_SECONDS)
            response.raise_for_status()
            MODEL_PATH.write_bytes(response.content)
        _model = fasttext.load_model(str(MODEL_PATH))
    except Exception:
        logger.exception("failed to load language-ID model -- language filtering disabled for this process")
        _load_failed = True
    return _model


def detect_language(text: str) -> tuple[str, float]:
    """(label, confidence) -- ("", 0.0) for blank text or if the model
    couldn't be loaded.

    Calls the underlying pybind11 binding's predict() directly rather than
    going through FastText.py's own predict() wrapper: that wrapper's
    final `np.array(probs, copy=False)` conversion raises under
    numpy>=2.0 (this project's pinned floor) -- a known, unfixed issue in
    the unmaintained fasttext/fasttext-wheel packages. The underlying
    call already returns plain Python (probability, label) tuples, so
    going around the wrapper avoids numpy for this one call entirely;
    nothing else about the prediction changes.
    """
    normalized = text.replace("\n", " ").strip()
    if not normalized:
        return "", 0.0
    model = _get_model()
    if model is None:
        return "", 0.0
    predictions = model.f.predict(normalized, 1, 0.0, "strict")
    if not predictions:
        return "", 0.0
    prob, label = predictions[0]
    return label.replace("__label__", ""), float(prob)


def is_non_english(text: str) -> bool:
    """True only when confidently non-English. Blank text, an unloadable
    model, and low-confidence guesses on short/ambiguous content all fall
    through as "not confidently non-English" (i.e. kept) -- same "don't
    exclude on a weak signal" caution as bot_filter.py's
    velocity-alone-can't-flag rule.

    Called from pipeline.py in two cases: any post with no self-reported
    language tag at all (issue #28 -- there's no metadata to fall back on
    if the content itself is inconclusive), and every Mastodon post
    regardless of its tag (issue #41 -- unlike Bluesky's poster-set langs,
    Mastodon's server-reported language can be defaulted wrong by an
    automated posting tool, confirmed at a real ~6% rate in production).
    Deliberately NOT extended to Bluesky's tagged posts -- tested against
    real data and found to trade a small, mostly-illusory gap for a real
    false-positive problem on short, casual English text."""
    label, confidence = detect_language(text)
    return label != "" and label != "en" and confidence >= CONFIDENCE_THRESHOLD
