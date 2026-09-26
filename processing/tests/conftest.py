import pytest

import config
from infra import degradation


@pytest.fixture(autouse=True)
def _no_local_models_dir(monkeypatch):
    """A developer's processing/.env may set LOCAL_MODELS_DIR -- keep every
    test on the R2/injected-store paths unless it opts in itself."""
    monkeypatch.setattr(config, "LOCAL_MODELS_DIR", None)


@pytest.fixture(autouse=True)
def _reset_degradation_state():
    """degradation.py's module-level state is process-global by design (it
    answers "is anything degraded right now", not a durable log) -- reset
    it before every test so one test's simulated Redis failure can't leak
    into another test's assertions via import order."""
    degradation._last_degradation.clear()
    degradation._last_cycle_success_at = None
    yield


@pytest.fixture
def fixture_quality_onnx_bytes() -> bytes:
    """A real, tiny TF-IDF + binary LogisticRegression pipeline, trained on
    trivial synthetic data and exported via skl2onnx exactly like the real
    training notebook -- same reasoning as fixture_political_onnx_bytes,
    since quality_model.py's target is also binary (genuinely-uplifting-
    and-substantive vs. everything else)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import StringTensorType

    texts = [
        "a local shelter found homes for 40 rescue dogs this weekend",
        "scientists mapped a previously unknown coral reef ecosystem",
        "happy friday everyone",
        "good morning",
    ] * 5
    labels = [1, 1, 0, 0] * 5

    vectorizer = TfidfVectorizer()
    clf = LogisticRegression(max_iter=1000)
    pipeline = Pipeline([("tfidf", vectorizer), ("clf", clf)])
    pipeline.fit(texts, labels)

    onnx_model = convert_sklearn(
        pipeline,
        initial_types=[("input", StringTensorType([None, 1]))],
        options={id(clf): {"zipmap": False}},
    )
    return onnx_model.SerializeToString()


@pytest.fixture
def fixture_political_onnx_bytes() -> bytes:
    """A real, tiny TF-IDF + binary LogisticRegression pipeline, trained on
    trivial synthetic data and exported via skl2onnx exactly like the real
    training notebook, rather than a hand-built ONNX graph -- string-keyed
    lookup has no simple built-in ONNX primitive, and this exercises the
    real conversion path, not an approximation of it."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import StringTensorType

    texts = [
        "the senate voted on the new bill today",
        "the president signed the executive order",
        "tried a new recipe for homemade pasta tonight",
        "went for a long walk in the park today",
    ] * 5
    labels = [1, 1, 0, 0] * 5

    vectorizer = TfidfVectorizer()
    clf = LogisticRegression(max_iter=1000)
    pipeline = Pipeline([("tfidf", vectorizer), ("clf", clf)])
    pipeline.fit(texts, labels)

    onnx_model = convert_sklearn(
        pipeline,
        initial_types=[("input", StringTensorType([None, 1]))],
        options={id(clf): {"zipmap": False}},
    )
    return onnx_model.SerializeToString()
