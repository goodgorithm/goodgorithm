import logging
import re

import gensim.downloader as gensim_api
import numpy as np

import config
from infra import model_store

logger = logging.getLogger("processing")

# None until loaded -- there is no fallback, so political_centroid_score simply isn't available on any
# post while this is unset. Set to "nearest_centroid_v1" on a successful
# load. Mirrors political_model.py's POLITICAL_METHOD convention.
POLITICAL_CENTROID_METHOD: str | None = None
POLITICAL_CENTROID_MODEL_LOADED_VERSION: str | None = None

# gensim's own KeyedVectors, not an ONNX session -- this is a raw word-
# embedding table (~400-500MB in memory), not a trained artifact of ours.
# Loaded once per process, same lazy-load-once discipline as every other
# model here; a process restart/redeploy re-downloads it from gensim's own
# remote host (not R2) -- a real, accepted cold-start cost.
_embeddings = None
_political_centroid: np.ndarray | None = None
_non_political_centroid: np.ndarray | None = None
_load_attempted = False

_TOKEN_RE = re.compile(r"[a-zA-Z']+")


def _tokenize(text: str) -> list[str]:
    # Deliberately not util.text_normalize.normalize_text() -- the centroids
    # are fit and thresholded against this exact plain lowercase-regex
    # tokenization; switching to the normalized form would silently shift
    # which words a post's mean vector is built from and invalidate the
    # threshold without a fresh evaluation.
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _mean_vector(tokens: list[str]) -> np.ndarray | None:
    vecs = [_embeddings[t] for t in tokens if t in _embeddings]
    if not vecs:
        return None
    return np.mean(vecs, axis=0)


def _cosine(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None:
        return 0.0
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def load_model(store: model_store.ModelStore | None = None) -> None:
    """Attempts to load the political/non-political centroid vectors from
    the configured model source (R2, or LOCAL_MODELS_DIR -- see
    model_store.default_store), plus the word embeddings needed to score
    incoming posts against them (downloaded by gensim into GENSIM_DATA_DIR,
    not from the model source). On any failure — no source configured,
    network error, missing/
    corrupt objects, the embeddings download failing — logs once and leaves
    the centroid signal unavailable. Mirrors political_model.py's
    load_model() shape."""
    global _embeddings, _political_centroid, _non_political_centroid
    global POLITICAL_CENTROID_METHOD, POLITICAL_CENTROID_MODEL_LOADED_VERSION

    if store is None:
        store = model_store.default_store("political-centroid")
        if store is None:
            logger.info("no model source configured — political centroid signal unavailable")
            return

    try:
        version = config.POLITICAL_CENTROID_MODEL_VERSION or store.resolve_version()
        centroid_config = store.get_json(f"{store.prefix}/{version}/centroids.json")
        political_centroid = np.array(centroid_config["political_centroid"], dtype=np.float32)
        non_political_centroid = np.array(centroid_config["non_political_centroid"], dtype=np.float32)
        embeddings = gensim_api.load(centroid_config["embedding"])
    except Exception:
        logger.exception("failed to load political centroid signal — score stays unavailable")
        return

    _embeddings = embeddings
    _political_centroid = political_centroid
    _non_political_centroid = non_political_centroid
    POLITICAL_CENTROID_METHOD = "nearest_centroid_v1"
    POLITICAL_CENTROID_MODEL_LOADED_VERSION = version
    logger.info("loaded political centroid signal %s (%s)", version, type(store).__name__)


def _ensure_loaded() -> None:
    global _load_attempted
    if not _load_attempted:
        _load_attempted = True
        load_model()


def score_batch(posts: list) -> dict:
    """Per-post cosine(political centroid) - cosine(non-political centroid).
    Returns {} for every post.id if the signal isn't loaded, same contract
    as political_model.score_batch(). No batched embedding-lookup API in
    gensim worth using here — each post's mean vector is cheap (a handful of
    dictionary lookups), unlike the classifier's one-ONNX-call-per-batch."""
    if not posts:
        return {}

    _ensure_loaded()

    if _embeddings is None:
        return {}

    results = {}
    for post in posts:
        vector = _mean_vector(_tokenize(post.text))
        results[post.id] = _cosine(vector, _political_centroid) - _cosine(vector, _non_political_centroid)
    return results
