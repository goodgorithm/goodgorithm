import logging

import numpy as np
import onnxruntime as ort

import config
from infra import model_store
from pipeline_stages import taxonomy
from text_normalize import normalize_text

logger = logging.getLogger("processing")

# Bumped to "tfidf_lr_v1" on a successful model load -- stored alongside
# every category assignment so keyword_v1/tfidf_lr_v1 results are
# distinguishable in processed_posts. Mirrors sentiment.py's
# SENTIMENT_METHOD exactly -- see the wiki's Categorization page.
CATEGORY_METHOD = "keyword_v1"

_session: ort.InferenceSession | None = None
_labels: list[str] | None = None
_threshold: float = 0.0
_load_attempted = False


def load_model(store: model_store.ModelStore | None = None) -> None:
    """Attempts to load the trained classifier from R2. On any failure —
    R2 not configured, network error, missing/corrupt objects, a label-
    order mismatch — logs once and leaves the keyword-matcher path active.
    Mirrors sentiment.py's load_model() shape exactly. See the wiki's
    Categorization page."""
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

        # Catches a silent-wrong-answer failure a static shape check
        # wouldn't -- see the wiki's Categorization page.
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


def _ensure_loaded() -> None:
    global _load_attempted
    if not _load_attempted:
        _load_attempted = True
        load_model()


def _categorize_with_model_batch(texts: list[str]) -> list[str | None]:
    """One ONNX call for the whole batch -- viable because the classifier's
    exported graph has a dynamic batch dimension (StringTensorType([None,
    1])), unlike sentiment.py's CNN which is fixed at batch=1. See the
    wiki's Categorization page."""
    normalized = [normalize_text(t) for t in texts]
    outputs = _session.run(["probabilities"], {"input": np.array([[t] for t in normalized], dtype=object)})
    probs = outputs[0]
    results = []
    for row in probs:
        best_idx = int(np.argmax(row))
        results.append(_labels[best_idx] if row[best_idx] >= _threshold else None)
    return results


def _categorize_with_model(text: str) -> str | None:
    return _categorize_with_model_batch([text])[0]


def categorize_batch(posts: list, topicality_results: dict) -> dict:
    """Batched form of categorize() -- run_cycle calls this once per cycle
    instead of categorize() in a per-post loop. See the wiki's
    Categorization page."""
    if not posts:
        return {}

    _ensure_loaded()

    if _session is not None:
        categories = _categorize_with_model_batch([post.text for post in posts])
        return {post.id: category for post, category in zip(posts, categories)}

    return {
        post.id: taxonomy.categorize(
            topicality_results[post.id].entities,
            topicality_results[post.id].top_terms,
            normalize_text(post.text),
        )
        for post in posts
    }


def categorize(text: str, entities: list[str], top_terms: list[str]) -> str | None:
    """Category for a post: the trained classifier if loaded, taxonomy.py's
    keyword matcher otherwise. Single-post convenience wrapper -- run_cycle
    uses categorize_batch() directly. Same lazy-load-once discipline as
    sentiment.py's score_sentiment(). See the wiki's Categorization page."""
    _ensure_loaded()

    if _session is not None:
        return _categorize_with_model(text)
    return taxonomy.categorize(entities, top_terms, normalize_text(text))
