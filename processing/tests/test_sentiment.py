from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from pipeline_stages import sentiment


@dataclass
class FakePost:
    id: UUID
    text: str


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
        self.resolve_version_calls = 0

    def resolve_version(self) -> str:
        self.resolve_version_calls += 1
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

    def fake_construct(prefix):
        assert prefix == "sentiment-cnn"
        construct_count["n"] += 1
        return store

    monkeypatch.setattr(sentiment.config, "r2_configured", lambda: True)
    monkeypatch.setattr(sentiment.model_store, "R2ModelStore", fake_construct)

    sentiment.score_sentiment("goodword")
    sentiment.score_sentiment("goodword")

    assert construct_count["n"] == 1
    assert sentiment.SENTIMENT_METHOD == "cnn_v1"


def test_score_sentiment_batch_empty_returns_empty_dict():
    assert sentiment.score_sentiment_batch([]) == {}


def test_score_sentiment_batch_matches_per_post_score_with_vader_fallback():
    posts = [
        FakePost(id=uuid4(), text="I love this, it's absolutely wonderful and amazing!"),
        FakePost(id=uuid4(), text="This is terrible, I hate it, everything is awful."),
    ]

    results = sentiment.score_sentiment_batch(posts)

    assert results[posts[0].id] > 0.5
    assert results[posts[1].id] < -0.5
    assert sentiment.SENTIMENT_METHOD == "vader_v1"


def test_score_sentiment_batch_uses_trained_model_after_successful_load(fixture_onnx_bytes, fixture_vocab):
    store = FakeModelStore(fixture_onnx_bytes, fixture_vocab)
    sentiment.load_model(store)

    posts = [
        FakePost(id=uuid4(), text="goodword"),
        FakePost(id=uuid4(), text="okword"),
    ]

    results = sentiment.score_sentiment_batch(posts)

    # "goodword" -> vocab id 1 -> fixture prob_table row 1 = [0.1, 0.2, 0.7]
    assert results[posts[0].id] == pytest.approx(0.6, abs=1e-4)
    # "okword" -> vocab id 2 -> fixture prob_table row 2 = [0.2, 0.6, 0.2]
    assert results[posts[1].id] == pytest.approx(0.0, abs=1e-4)


def test_score_sentiment_batch_matches_single_post_score_call_for_call(fixture_onnx_bytes, fixture_vocab):
    # The batched ONNX call must produce identical per-post results to the
    # single-post path -- proves batching is a pure performance change.
    store = FakeModelStore(fixture_onnx_bytes, fixture_vocab)
    sentiment.load_model(store)

    texts = ["goodword", "okword", "goodword okword"]
    posts = [FakePost(id=uuid4(), text=text) for text in texts]

    batch_results = sentiment.score_sentiment_batch(posts)
    individual_results = {post.id: sentiment.score_sentiment(post.text) for post in posts}

    assert batch_results == individual_results


def test_load_model_uses_env_override_without_hitting_r2(fixture_onnx_bytes, fixture_vocab):
    # SENTIMENT_MODEL_VERSION set -> resolve_version() (the network call)
    # should never be reached at all, not just its result ignored.
    store = FakeModelStore(fixture_onnx_bytes, fixture_vocab, version="v1")
    original = sentiment.config.SENTIMENT_MODEL_VERSION
    sentiment.config.SENTIMENT_MODEL_VERSION = "v7-pinned"
    try:
        sentiment.load_model(store)
    finally:
        sentiment.config.SENTIMENT_MODEL_VERSION = original

    assert store.resolve_version_calls == 0
    assert sentiment.SENTIMENT_METHOD == "cnn_v1"
