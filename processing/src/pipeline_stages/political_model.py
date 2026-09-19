import logging

import numpy as np
import onnxruntime as ort

import config
from infra import model_store
from util.text_normalize import normalize_text

logger = logging.getLogger("processing")

# None until a model loads successfully -- unlike category_model.py/
# sentiment.py, there is no keyword-matcher-style fallback here, so
# political_score/political_method simply stay NULL on every post while
# this is unset. Set to "tfidf_lr_v1" on a successful load.
POLITICAL_METHOD: str | None = None
# The resolved R2 version string, set alongside POLITICAL_METHOD on success.
POLITICAL_MODEL_LOADED_VERSION: str | None = None

_session: ort.InferenceSession | None = None
_political_label_index: int | None = None
_load_attempted = False


def load_model(store: model_store.ModelStore | None = None) -> None:
    """Attempts to load the trained classifier from R2. On any failure —
    R2 not configured, network error, missing/corrupt objects, a label-
    order mismatch — logs once and leaves political_score/political_method
    NULL for every post. Mirrors category_model.py's load_model() shape,
    minus the fallback (there is no cheap keyword equivalent worth building
    for political-topic detection)."""
    global _session, _political_label_index, POLITICAL_METHOD, POLITICAL_MODEL_LOADED_VERSION

    if store is None:
        if not config.r2_configured():
            logger.info("R2 not configured — political classifier unavailable")
            return
        store = model_store.R2ModelStore(prefix="political-classifier")

    try:
        version = config.POLITICAL_MODEL_VERSION or store.resolve_version()
        model_bytes = store.get_bytes(f"{store.prefix}/{version}/model.onnx")
        model_config = store.get_json(f"{store.prefix}/{version}/config.json")
        session = ort.InferenceSession(model_bytes, providers=["CPUExecutionProvider"])
        labels = model_config["labels"]
        political_label_index = labels.index("political")

        # Catches a silent-wrong-answer failure a static shape check
        # wouldn't -- same reasoning as category_model.py's smoke test.
        probe = session.run(["probabilities"], {"input": np.array([["smoke test"]], dtype=object)})
        probe_width = probe[0].shape[-1]
        if probe_width != len(labels):
            raise ValueError(
                f"ONNX output width {probe_width} doesn't match config.json's {len(labels)} labels"
            )
    except Exception:
        logger.exception("failed to load political classifier from R2 — political_score stays unset")
        return

    _session = session
    _political_label_index = political_label_index
    POLITICAL_METHOD = "tfidf_lr_v1"
    POLITICAL_MODEL_LOADED_VERSION = version
    logger.info("loaded political classifier %s", version)


def _ensure_loaded() -> None:
    global _load_attempted
    if not _load_attempted:
        _load_attempted = True
        load_model()


def score_batch(posts: list) -> dict:
    """Batched P(political) per post -- one ONNX call for the whole batch,
    same shape as category_model.categorize_batch(). Returns {} for every
    post.id if no model is loaded (R2 unconfigured, or load failed) rather
    than a partial/guessed score. Observational only for now: nothing
    reads this dict's values to exclude or devalue a post yet."""
    if not posts:
        return {}

    _ensure_loaded()

    if _session is None:
        return {}

    normalized = [normalize_text(post.text) for post in posts]
    outputs = _session.run(["probabilities"], {"input": np.array([[t] for t in normalized], dtype=object)})
    probs = outputs[0]
    return {post.id: float(row[_political_label_index]) for post, row in zip(posts, probs)}
