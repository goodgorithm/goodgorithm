import logging
import os
import re
import tempfile
import unicodedata
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

# Tuned against real production text -- see the wiki's Content Filtering
# page for what this trades off and why 0.3 specifically.
LANGUAGE_FILTER_CONFIDENCE_THRESHOLD = float(os.environ.get("LANGUAGE_FILTER_CONFIDENCE_THRESHOLD", "0.3"))

# Fraction of a post's letters that must be non-Latin for
# bluesky_tag_needs_recheck to override a self-reported `en` tag. A random
# production sample put real posts with a non-empty `langs` tag at ~1%
# predominantly non-Latin, essentially all genuinely non-English; non-Latin
# English text does not occur, so the fastText re-check this gates costs no
# real English. See CLAUDE.md's Non-English content filtering section.
LANGUAGE_FILTER_NON_LATIN_RATIO = float(os.environ.get("LANGUAGE_FILTER_NON_LATIN_RATIO", "0.5"))
# URLs, @mentions and #hashtags are stripped before the script check --
# they skew ASCII even in an otherwise fully non-Latin post.
_RECHECK_STRIP_RE = re.compile(r"https?://\S+|[@#]\S+")

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
    for every Mastodon post regardless of its tag, and -- via
    bluesky_tag_needs_recheck below -- for a Bluesky post whose own `langs`
    tag can't be trusted. See CLAUDE.md's Non-English content filtering
    section and the wiki's Content Policy page for why a Latin-script
    Bluesky post under an `en` tag is still exempt."""
    label, confidence = detect_language(text)
    return label != "" and label != "en" and confidence >= LANGUAGE_FILTER_CONFIDENCE_THRESHOLD


def is_english_lang_tag(lang: str | None) -> bool:
    """Whether a source-reported language tag names English. An absent tag
    (`None`) is not English here -- callers decide separately what to do
    with a missing tag. Region subtags (`en-US`, `en-GB`) count as English."""
    if lang is None:
        return False
    lang = lang.lower()
    return lang == "en" or lang.startswith("en-")


def is_predominantly_non_latin(text: str) -> bool:
    """True when at least LANGUAGE_FILTER_NON_LATIN_RATIO of the text's
    letters are outside the Latin script (CJK, Thai, Arabic, Cyrillic,
    Hangul, ...). A cheap string scan, no model. URLs / @mentions /
    #hashtags are stripped first; digits, emoji and punctuation don't
    count either way. Accented Latin (á, ñ, ö) stays Latin, so Spanish /
    German / French text is not flagged."""
    stripped = _RECHECK_STRIP_RE.sub(" ", text)
    letters = [ch for ch in stripped if ch.isalpha()]
    if not letters:
        return False
    non_latin = 0
    for ch in letters:
        try:
            if not unicodedata.name(ch).startswith("LATIN"):
                non_latin += 1
        except ValueError:  # unnamed char -- treat as non-Latin
            non_latin += 1
    return non_latin / len(letters) >= LANGUAGE_FILTER_NON_LATIN_RATIO


def bluesky_tag_needs_recheck(lang: str | None, text: str) -> bool:
    """Whether a self-tagged Bluesky post should still get the fastText
    non-English re-check. True when the tag can't be trusted: its primary
    self-reported language isn't English at all (`langs:["es","en"]` slips
    past ingestion because "en" is present in the array), or the text is
    predominantly non-Latin script (a wrong `langs:["en"]` on Thai / CJK /
    Arabic text is common in practice, and genuinely non-Latin English
    doesn't exist, so this costs ~no real English). A Latin-script post
    under an `en`/`en-*` tag is still trusted as-is -- that gap is left
    open on purpose; see CLAUDE.md's Non-English content filtering section."""
    if not is_english_lang_tag(lang):
        return True
    return is_predominantly_non_latin(text)
