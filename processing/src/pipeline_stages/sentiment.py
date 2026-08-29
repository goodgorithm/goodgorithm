import logging

import numpy as np
import onnxruntime as ort
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

import config
from infra import model_store
from util import sentiment_model

logger = logging.getLogger("processing")

# Bumped to "cnn_v1" on a successful model load — stored alongside every
# score so vader_v1/cnn_v1 results are distinguishable in processed_posts.
SENTIMENT_METHOD = "vader_v1"
# The resolved R2 version string ("v3", etc.), set alongside SENTIMENT_METHOD
# on success -- None while on VADER. Exists so the status endpoint can
# report which model version is actually live without digging through logs.
SENTIMENT_MODEL_LOADED_VERSION: str | None = None

# negative/neutral/positive -- architecturally fixed by sentiment_model.py's
# final nn.Linear(..., 3) layer, not something that varies by version the
# way category_model.py's label list can, so this is a hardcoded constant
# rather than a config.json field. Used only by load_model()'s smoke test
# below.
EXPECTED_NUM_CLASSES = 3

_analyzer: SentimentIntensityAnalyzer | None = None
_session: ort.InferenceSession | None = None
_vocab: dict | None = None
_load_attempted = False


def _get_analyzer() -> SentimentIntensityAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def load_model(store: model_store.ModelStore | None = None) -> None:
    """Attempts to load the trained CNN from R2. On any failure — R2 not
    configured, network error, missing/corrupt objects — logs once and
    leaves the VADER path active. score_sentiment() never raises because of
    this and never blocks waiting for R2 to recover mid-run. See the
    wiki's Sentiment page."""
    global _session, _vocab, SENTIMENT_METHOD, SENTIMENT_MODEL_LOADED_VERSION

    if store is None:
        if not config.r2_configured():
            logger.info("R2 not configured — sentiment CNN unavailable, using VADER")
            return
        store = model_store.R2ModelStore(prefix="sentiment-cnn")

    try:
        version = config.SENTIMENT_MODEL_VERSION or store.resolve_version()
        model_bytes, vocab, _model_config = store.fetch(version)
        session = ort.InferenceSession(model_bytes, providers=["CPUExecutionProvider"])

        # Smoke-test probe, mirroring category_model.py's label-order-
        # mismatch check -- catches a corrupted/mismatched export producing
        # a different-width output, a silent-wrong-answer failure a shape
        # check alone wouldn't otherwise catch until scores looked "off."
        # Only verifies width, not label order -- order-safety comes from
        # the training notebook's own export-time parity assertion, a
        # training-time guarantee between versions, not a runtime one
        # (the same limitation category_model.py's own width-only check has).
        probe_ids = np.zeros((1, sentiment_model.MAX_SEQ_LEN), dtype=np.int64)
        probe_width = session.run(None, {"input_ids": probe_ids})[0].shape[-1]
        if probe_width != EXPECTED_NUM_CLASSES:
            raise ValueError(f"ONNX output width {probe_width} != expected {EXPECTED_NUM_CLASSES} classes")
    except Exception:
        logger.exception("failed to load sentiment CNN from R2 — using VADER")
        return

    _session = session
    _vocab = vocab
    SENTIMENT_METHOD = "cnn_v1"
    SENTIMENT_MODEL_LOADED_VERSION = version
    logger.info("loaded sentiment CNN %s", version)


def _ensure_loaded() -> None:
    global _load_attempted
    if not _load_attempted:
        _load_attempted = True
        load_model()


def _score_with_cnn_batch(texts: list[str]) -> list[float]:
    """One ONNX call for the whole batch -- viable because the published
    model's ONNX graph has a dynamic batch dimension. Mirrors
    category_model.py's _categorize_with_model_batch shape exactly. See
    the wiki's Sentiment page."""
    encoded = [sentiment_model.encode(sentiment_model.tokenize(text), _vocab) for text in texts]
    input_ids = np.array(encoded, dtype=np.int64)
    # label order 0=negative, 1=neutral, 2=positive — fixed by the training
    # notebook's label mapping, baked into the exported graph's output.
    probs = _session.run(None, {"input_ids": input_ids})[0]
    return [float(row[2] - row[0]) for row in probs]  # P(positive) - P(negative); see the wiki


def _score_with_cnn(text: str) -> float:
    return _score_with_cnn_batch([text])[0]


def score_sentiment_batch(posts: list) -> dict:
    """Batched form of score_sentiment() -- run_cycle calls this once per
    cycle instead of score_sentiment() in a per-post loop. Mirrors
    category_model.py's categorize_batch() shape exactly. See the wiki's
    Sentiment page."""
    if not posts:
        return {}

    _ensure_loaded()

    if _session is not None:
        scores = _score_with_cnn_batch([post.text for post in posts])
        return {post.id: score for post, score in zip(posts, scores)}

    analyzer = _get_analyzer()
    return {post.id: analyzer.polarity_scores(post.text)["compound"] for post in posts}


def score_sentiment(text: str) -> float:
    """[-1, 1]. Lazily attempts to load the trained CNN once per process on
    first call; falls back to VADER if that fails or R2 isn't configured.
    The decision is made once, not retried per call, so a single process's
    output never mixes cnn_v1/vader_v1 labels. Single-post convenience
    wrapper -- run_cycle uses score_sentiment_batch() directly. See the
    wiki's Sentiment page."""
    _ensure_loaded()

    if _session is not None:
        return _score_with_cnn(text)
    return _get_analyzer().polarity_scores(text)["compound"]
