import pytest

import sentiment


@pytest.fixture(autouse=True)
def reset_sentiment_module_state(monkeypatch):
    """sentiment.py has module-global mutable state (the loaded CNN session,
    vocab, load-attempted flag, SENTIMENT_METHOD) so tests don't bleed into
    each other regardless of run order. Also forces r2_configured() False by
    default so tests are hermetic regardless of what's in a developer's
    local .env — tests that want the CNN path override this themselves."""
    sentiment._session = None
    sentiment._vocab = None
    sentiment._load_attempted = False
    sentiment.SENTIMENT_METHOD = "vader_v1"
    monkeypatch.setattr(sentiment.config, "r2_configured", lambda: False)
    yield
    sentiment._session = None
    sentiment._vocab = None
    sentiment._load_attempted = False
    sentiment.SENTIMENT_METHOD = "vader_v1"


class FakeModelStore:
    def __init__(self, model_bytes: bytes, vocab: dict, version: str = "v1"):
        self.model_bytes = model_bytes
        self.vocab = vocab
        self.version = version

    def resolve_version(self) -> str:
        return self.version

    def fetch(self, version: str):
        return self.model_bytes, self.vocab, {}


class FailingModelStore:
    def resolve_version(self) -> str:
        raise RuntimeError("simulated R2 outage")

    def fetch(self, version: str):
        raise RuntimeError("simulated R2 outage")


def test_score_sentiment_clearly_positive():
    score = sentiment.score_sentiment("I love this, it's absolutely wonderful and amazing!")
    assert score > 0.5


def test_score_sentiment_clearly_negative():
    score = sentiment.score_sentiment("This is terrible, I hate it, everything is awful.")
    assert score < -0.5


def test_score_sentiment_neutral():
    score = sentiment.score_sentiment("The meeting is scheduled for 3pm on Tuesday.")
    assert -0.2 < score < 0.2


def test_score_sentiment_bounded():
    assert -1.0 <= sentiment.score_sentiment("great") <= 1.0
    assert -1.0 <= sentiment.score_sentiment("terrible") <= 1.0


def test_score_sentiment_empty_text():
    assert sentiment.score_sentiment("") == 0.0


def test_load_model_success_switches_method_to_cnn(fixture_onnx_bytes, fixture_vocab):
    store = FakeModelStore(fixture_onnx_bytes, fixture_vocab)
    sentiment.load_model(store)
    assert sentiment.SENTIMENT_METHOD == "cnn_v1"


def test_score_sentiment_uses_cnn_after_successful_load(fixture_onnx_bytes, fixture_vocab):
    store = FakeModelStore(fixture_onnx_bytes, fixture_vocab)
    sentiment.load_model(store)
    # "goodword" -> vocab id 1 -> fixture prob_table row 1 = [0.1, 0.2, 0.7]
    # score = P(positive) - P(negative) = 0.7 - 0.1
    score = sentiment.score_sentiment("goodword")
    assert score == pytest.approx(0.6, abs=1e-4)


def test_load_model_failure_falls_back_to_vader():
    sentiment.load_model(FailingModelStore())
    assert sentiment.SENTIMENT_METHOD == "vader_v1"
    score = sentiment.score_sentiment("great")
    assert -1.0 <= score <= 1.0


def test_score_sentiment_lazy_loads_once(monkeypatch, fixture_onnx_bytes, fixture_vocab):
    store = FakeModelStore(fixture_onnx_bytes, fixture_vocab)
    construct_count = {"n": 0}

    def fake_construct():
        construct_count["n"] += 1
        return store

    monkeypatch.setattr(sentiment.config, "r2_configured", lambda: True)
    monkeypatch.setattr(sentiment.model_store, "R2ModelStore", fake_construct)

    sentiment.score_sentiment("goodword")
    sentiment.score_sentiment("goodword")

    assert construct_count["n"] == 1
    assert sentiment.SENTIMENT_METHOD == "cnn_v1"
