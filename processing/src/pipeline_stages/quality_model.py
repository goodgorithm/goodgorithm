import logging

import numpy as np
import onnxruntime as ort

import config
from infra import model_store
from util.text_normalize import normalize_text

logger = logging.getLogger("processing")

# None until a model loads successfully -- same reasoning as
# political_model.py: no fallback exists for "would a human call this
# good", so quality_score/quality_method simply stay NULL for every post
# while this is unset. Set to "tfidf_lr_v1" on a successful load.
QUALITY_METHOD: str | None = None
# The resolved R2 version string, set alongside QUALITY_METHOD on success.
QUALITY_MODEL_LOADED_VERSION: str | None = None

_session: ort.InferenceSession | None = None
_quality_label_index: int | None = None
_load_attempted = False


def load_model(store: model_store.ModelStore | None = None) -> None:
    """Attempts to load the trained classifier from R2. On any failure —
    R2 not configured, network error, missing/corrupt objects, a label-
    order mismatch — logs once and leaves quality_score/quality_method
    NULL for every post. Mirrors political_model.py's load_model() shape
    exactly, minus the label name (genuinely_uplifting_and_substantive
    instead of political)."""
    global _session, _quality_label_index, QUALITY_METHOD, QUALITY_MODEL_LOADED_VERSION

    if store is None:
        if not config.r2_configured():
            logger.info("R2 not configured — quality classifier unavailable")
            return
        store = model_store.R2ModelStore(prefix="quality-classifier")

    try:
        version = config.QUALITY_MODEL_VERSION or store.resolve_version()
        model_bytes = store.get_bytes(f"{store.prefix}/{version}/model.onnx")
        model_config = store.get_json(f"{store.prefix}/{version}/config.json")
        session = ort.InferenceSession(model_bytes, providers=["CPUExecutionProvider"])
        labels = model_config["labels"]
        quality_label_index = labels.index("genuinely_uplifting_and_substantive")

        # Catches a silent-wrong-answer failure a static shape check
        # wouldn't -- same reasoning as category_model.py's smoke test.
        probe = session.run(["probabilities"], {"input": np.array([["smoke test"]], dtype=object)})
        probe_width = probe[0].shape[-1]
        if probe_width != len(labels):
            raise ValueError(
                f"ONNX output width {probe_width} doesn't match config.json's {len(labels)} labels"
            )
    except Exception:
        logger.exception("failed to load quality classifier from R2 — quality_score stays unset")
        return

    _session = session
    _quality_label_index = quality_label_index
    QUALITY_METHOD = "tfidf_lr_v1"
    QUALITY_MODEL_LOADED_VERSION = version
    logger.info("loaded quality classifier %s", version)


def _ensure_loaded() -> None:
    global _load_attempted
    if not _load_attempted:
        _load_attempted = True
        load_model()


def score_batch(posts: list) -> dict:
    """Batched P(genuinely-uplifting-and-substantive) per post -- one ONNX
    call for the whole batch, same shape as political_model.score_batch().
    Returns {} for every post.id if no model is loaded (R2 unconfigured, or
    load failed) rather than a partial/guessed score. Consumed by
    quality_exclude.py's hard-exclude gate in pipeline.py's run_cycle,
    right after the political exclude block."""
    if not posts:
        return {}

    _ensure_loaded()

    if _session is None:
        return {}

    normalized = [normalize_text(post.text) for post in posts]
    outputs = _session.run(["probabilities"], {"input": np.array([[t] for t in normalized], dtype=object)})
    probs = outputs[0]
    return {post.id: float(row[_quality_label_index]) for post, row in zip(posts, probs)}
