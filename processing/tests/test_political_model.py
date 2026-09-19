from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from pipeline_stages import political_model


@dataclass
class FakePost:
    id: UUID
    text: str


@pytest.fixture(autouse=True)
def reset_political_module_state(monkeypatch):
    """political_model.py has module-global mutable state (the loaded
    session, label index, load-attempted flag, POLITICAL_METHOD) so tests
    don't bleed into each other regardless of run order. Also forces
    r2_configured() False by default so tests are hermetic regardless of
    what's in a developer's local .env -- tests that want the classifier
    path override this themselves. Mirrors test_category_model.py's
    equivalent fixture."""
    political_model._session = None
    political_model._political_label_index = None
    political_model._load_attempted = False
    political_model.POLITICAL_METHOD = None
    political_model.POLITICAL_MODEL_LOADED_VERSION = None
    monkeypatch.setattr(political_model.config, "r2_configured", lambda: False)
    yield
    political_model._session = None
    political_model._political_label_index = None
    political_model._load_attempted = False
    political_model.POLITICAL_METHOD = None
    political_model.POLITICAL_MODEL_LOADED_VERSION = None


class FakeModelStore:
    def __init__(self, model_bytes: bytes, config: dict, version: str = "v1"):
        self.model_bytes = model_bytes
        self.model_config = config
        self.version = version
        self.prefix = "political-classifier"
        self.resolve_version_calls = 0
        self.requested_keys: list[str] = []

    def resolve_version(self) -> str:
        self.resolve_version_calls += 1
        return self.version

    def get_bytes(self, key: str) -> bytes:
        self.requested_keys.append(key)
        assert key.startswith(self.prefix) and key.endswith("/model.onnx")
        return self.model_bytes

    def get_json(self, key: str) -> dict:
        self.requested_keys.append(key)
        assert key.startswith(self.prefix) and key.endswith("/config.json")
        return self.model_config


class FailingModelStore:
    def resolve_version(self) -> str:
        raise RuntimeError("simulated R2 outage")


def _config(labels=("non-political", "political"), threshold=0.5):
    return {"labels": list(labels), "confidence_threshold": threshold}


def test_score_batch_empty_posts_returns_empty_dict():
    assert political_model.score_batch([]) == {}


def test_score_batch_returns_empty_dict_when_r2_unconfigured():
    posts = [FakePost(id=uuid4(), text="the senate voted on the new bill today")]
    assert political_model.score_batch(posts) == {}
    assert political_model.POLITICAL_METHOD is None


def test_load_model_success_sets_method_and_version(fixture_political_onnx_bytes):
    store = FakeModelStore(fixture_political_onnx_bytes, _config(), version="v3")
    political_model.load_model(store)
    assert political_model.POLITICAL_METHOD == "tfidf_lr_v1"
    assert political_model.POLITICAL_MODEL_LOADED_VERSION == "v3"


def test_load_model_failure_leaves_method_unset():
    political_model.load_model(FailingModelStore())
    assert political_model.POLITICAL_METHOD is None
    posts = [FakePost(id=uuid4(), text="the senate voted on the new bill today")]
    assert political_model.score_batch(posts) == {}


def test_load_model_rejects_label_order_mismatch(fixture_political_onnx_bytes):
    # config.json claims 3 labels but the model only outputs 2 -- the
    # silent-wrong-answer failure mode this check exists to catch.
    store = FakeModelStore(fixture_political_onnx_bytes, _config(labels=("non-political", "political", "extra")))
    political_model.load_model(store)
    assert political_model.POLITICAL_METHOD is None


def test_load_model_rejects_config_missing_political_label(fixture_political_onnx_bytes):
    # A config.json that doesn't even have "political" in its labels list --
    # labels.index() raises, caught by the same broad except as any other
    # load failure.
    store = FakeModelStore(fixture_political_onnx_bytes, _config(labels=("yes", "no")))
    political_model.load_model(store)
    assert political_model.POLITICAL_METHOD is None


def test_score_batch_uses_trained_model_after_successful_load(fixture_political_onnx_bytes):
    store = FakeModelStore(fixture_political_onnx_bytes, _config())
    political_model.load_model(store)

    posts = [
        FakePost(id=uuid4(), text="the senate voted on the new bill today"),
        FakePost(id=uuid4(), text="went for a long walk in the park today"),
    ]
    results = political_model.score_batch(posts)

    assert set(results) == {post.id for post in posts}
    assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in results.values())
    # Not asserting which side of 0.5 each lands on -- a handful of trivial
    # training examples doesn't guarantee a stable decision boundary, only
    # that scoring plumbing (label index, batch shape) is wired correctly.


def test_score_batch_lazy_loads_once(monkeypatch, fixture_political_onnx_bytes):
    store = FakeModelStore(fixture_political_onnx_bytes, _config())
    construct_count = {"n": 0}

    def fake_construct(prefix):
        assert prefix == "political-classifier"
        construct_count["n"] += 1
        return store

    monkeypatch.setattr(political_model.config, "r2_configured", lambda: True)
    monkeypatch.setattr(political_model.model_store, "R2ModelStore", fake_construct)

    posts = [FakePost(id=uuid4(), text="the senate voted on the new bill today")]
    political_model.score_batch(posts)
    political_model.score_batch(posts)

    assert construct_count["n"] == 1
    assert political_model.POLITICAL_METHOD == "tfidf_lr_v1"


def test_load_model_uses_env_override_without_hitting_r2(fixture_political_onnx_bytes):
    store = FakeModelStore(fixture_political_onnx_bytes, _config(), version="v1")
    original = political_model.config.POLITICAL_MODEL_VERSION
    political_model.config.POLITICAL_MODEL_VERSION = "v7-pinned"
    try:
        political_model.load_model(store)
    finally:
        political_model.config.POLITICAL_MODEL_VERSION = original

    assert store.resolve_version_calls == 0
    assert political_model.POLITICAL_METHOD == "tfidf_lr_v1"
    assert all("v7-pinned" in key for key in store.requested_keys)
