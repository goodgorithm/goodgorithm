import logging

import numpy as np
import onnxruntime as ort
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

import config
import sentiment_model
from infra import model_store

logger = logging.getLogger("processing")

# Bumped to "cnn_v1" on a successful model load — stored alongside every
# score so vader_v1/cnn_v1 results are distinguishable in processed_posts.
SENTIMENT_METHOD = "vader_v1"

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
    this and never blocks waiting for R2 to recover mid-run."""
    global _session, _vocab, SENTIMENT_METHOD

    if store is None:
        if not config.r2_configured():
            logger.info("R2 not configured — sentiment CNN unavailable, using VADER")
            return
        store = model_store.R2ModelStore(prefix="sentiment-cnn")

    try:
        version = config.SENTIMENT_MODEL_VERSION or store.resolve_version()
        model_bytes, vocab, _model_config = store.fetch(version)
        session = ort.InferenceSession(model_bytes, providers=["CPUExecutionProvider"])
    except Exception:
        logger.exception("failed to load sentiment CNN from R2 — using VADER")
        return

    _session = session
    _vocab = vocab
    SENTIMENT_METHOD = "cnn_v1"
    logger.info("loaded sentiment CNN %s", version)


def _score_with_cnn(text: str) -> float:
    ids = sentiment_model.encode(sentiment_model.tokenize(text), _vocab)
    input_ids = np.array([ids], dtype=np.int64)
    # label order 0=negative, 1=neutral, 2=positive — fixed by the training
    # notebook's label mapping, baked into the exported graph's output.
    probs = _session.run(None, {"input_ids": input_ids})[0][0]
    return float(probs[2] - probs[0])


def score_sentiment(text: str) -> float:
    """[-1, 1]. Lazily attempts to load the trained CNN once per process on
    first call; falls back to VADER if that fails or R2 isn't configured.
    The decision is made once, not retried per call, so a single process's
    output never mixes cnn_v1/vader_v1 labels."""
    global _load_attempted
    if not _load_attempted:
        _load_attempted = True
        load_model()

    if _session is not None:
        return _score_with_cnn(text)
    return _get_analyzer().polarity_scores(text)["compound"]
