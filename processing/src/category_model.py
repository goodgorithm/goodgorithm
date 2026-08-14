import logging

import numpy as np
import onnxruntime as ort

import config
import model_store
import taxonomy
from text_normalize import normalize_text

logger = logging.getLogger("processing")

# Bumped to "tfidf_lr_v1" on a successful model load -- stored alongside
# every category assignment so keyword_v1/tfidf_lr_v1 results are
# distinguishable in processed_posts, mirroring sentiment.py's
# SENTIMENT_METHOD. One process-wide flag, not a per-post choice: once the
# trained classifier is loaded, it's what runs, full stop -- the classifier
# is treated as a fully viable production component, the same standing as
# the sentiment CNN, not second-guessed post by post. taxonomy.py is the
# whole-process fallback for when the model can't load at all (R2
# unconfigured, network failure, etc.), the direct parallel to VADER's role.
CATEGORY_METHOD = "keyword_v1"

_session: ort.InferenceSession | None = None
_labels: list[str] | None = None
_threshold: float = 0.0
_load_attempted = False


def load_model(store: model_store.ModelStore | None = None) -> None:
    """Attempts to load the trained classifier from R2. On any failure —
    R2 not configured, network error, missing/corrupt objects, a label-
    order mismatch — logs once and leaves the keyword-matcher path active.
    categorize() never raises because of this and never blocks waiting for
    R2 to recover mid-run. Mirrors sentiment.py's load_model() shape
    exactly."""
    global _session, _labels, _threshold, CATEGORY_METHOD

    if store is None:
        if not config.r2_configured():
            logger.info("R2 not configured — category classifier unavailable, using keyword matcher")
            return
        store = model_store.R2ModelStore(prefix="category-classifier")

    try:
        version = config.CATEGORY_MODEL_VERSION or store.resolve_version()
        model_bytes = store.get_bytes(f"{store.prefix}/{version}/model.onnx")
        model_config = store.get_json(f"{store.prefix}/{version}/config.json")
        session = ort.InferenceSession(model_bytes, providers=["CPUExecutionProvider"])
        labels = model_config["labels"]

        # Label-order mismatch is a silent-wrong-answer failure (model
        # loads fine, confidently mislabels everything), not a crash — the
        # training notebook already asserts this at export time, but a
        # corrupt/mismatched config.json published later wouldn't be
        # caught without re-checking here, against the model's actual
        # runtime output (not just its static declared shape).
        probe = session.run(["probabilities"], {"input": np.array([["smoke test"]], dtype=object)})
        probe_width = probe[0].shape[-1]
        if probe_width != len(labels):
            raise ValueError(
                f"ONNX output width {probe_width} doesn't match config.json's {len(labels)} labels"
            )
    except Exception:
        logger.exception("failed to load category classifier from R2 — using keyword matcher")
        return

    _session = session
    _labels = labels
    _threshold = model_config["confidence_threshold"]
    CATEGORY_METHOD = "tfidf_lr_v1"
    logger.info("loaded category classifier %s", version)


def _categorize_with_model(text: str) -> str | None:
    normalized = normalize_text(text)
    outputs = _session.run(["probabilities"], {"input": np.array([[normalized]], dtype=object)})
    probs = outputs[0][0]
    best_idx = int(np.argmax(probs))
    return _labels[best_idx] if probs[best_idx] >= _threshold else None


def categorize(text: str, entities: list[str], top_terms: list[str]) -> str | None:
    """Category for a post: the trained classifier if loaded, taxonomy.py's
    keyword matcher otherwise. Lazily attempts to load the trained model
    once per process on first call, same "decided once, not retried per
    call" discipline as sentiment.py's score_sentiment() — a single
    process's output never mixes tfidf_lr_v1/keyword_v1 labels.

    The trained model sees the raw normalized post text directly, not
    topicality.py's pre-reduced ≤6-token top_terms/entities pool — that
    reduction only exists to make taxonomy.py's *exact* keyword matching
    tractable, and is itself the recall ceiling this classifier exists to
    fix."""
    global _load_attempted
    if not _load_attempted:
        _load_attempted = True
        load_model()

    if _session is not None:
        return _categorize_with_model(text)
    return taxonomy.categorize(entities, top_terms, normalize_text(text))
