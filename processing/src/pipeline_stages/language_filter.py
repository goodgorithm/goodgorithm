import logging
import os
import tempfile
from pathlib import Path

import fasttext
import requests

logger = logging.getLogger("processing")

# Meta's official pretrained language-ID model (176 languages). Chosen
# over lingua-py after benchmarking both against real production text --
# see CLAUDE.md's Non-English content filtering section and the wiki's
# Content Policy page for the full comparison and why. Fetched at runtime
# rather than committed to the repo (this project's .gitignore convention
# for ML artifacts), same fetch-a-pinned-third-party-artifact shape
# pyproject.toml uses for en_core_web_sm's wheel URL -- MODEL_URL is a
# version pin baked into code for the same reason that one is, not an env
# var. MODEL_PATH isn't a hardcoded location either: tempfile.gettempdir()
# already respects TMPDIR/TEMP/TMP if a deployment needs to redirect it.
MODEL_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz"
MODEL_PATH = Path(tempfile.gettempdir()) / "lid.176.ftz"
LANGUAGE_FILTER_FETCH_TIMEOUT_SECONDS = int(os.environ.get("LANGUAGE_FILTER_FETCH_TIMEOUT_SECONDS", "30"))

# Tuned against real production text -- see the wiki's Pipeline Internals
# page for what this trades off and why 0.3 specifically.
LANGUAGE_FILTER_CONFIDENCE_THRESHOLD = float(os.environ.get("LANGUAGE_FILTER_CONFIDENCE_THRESHOLD", "0.3"))

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
            response = requests.get(MODEL_URL, timeout=LANGUAGE_FILTER_FETCH_TIMEOUT_SECONDS)
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

    Called from pipeline.py for posts with no self-reported language tag,
    and for every Mastodon post regardless of its tag -- see CLAUDE.md's
    Non-English content filtering section and the wiki's Content Policy
    page for why, including why this is deliberately NOT extended to
    Bluesky's tagged posts."""
    label, confidence = detect_language(text)
    return label != "" and label != "en" and confidence >= LANGUAGE_FILTER_CONFIDENCE_THRESHOLD
