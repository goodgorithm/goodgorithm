from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from pipeline_stages import quality_model


@dataclass
class FakePost:
    id: UUID
    text: str


@pytest.fixture(autouse=True)
def reset_quality_module_state(monkeypatch):
    """quality_model.py has module-global mutable state (the loaded
    session, label index, load-attempted flag, QUALITY_METHOD) so tests
    don't bleed into each other regardless of run order. Also forces
    r2_configured() False by default so tests are hermetic regardless of
    what's in a developer's local .env -- tests that want the classifier
    path override this themselves. Mirrors test_political_model.py's
    equivalent fixture."""
    quality_model._session = None
    quality_model._quality_label_index = None
    quality_model._load_attempted = False
    quality_model.QUALITY_METHOD = None
    quality_model.QUALITY_MODEL_LOADED_VERSION = None
    monkeypatch.setattr(quality_model.config, "r2_configured", lambda: False)
    yield
    quality_model._session = None
    quality_model._quality_label_index = None
    quality_model._load_attempted = False
    quality_model.QUALITY_METHOD = None
    quality_model.QUALITY_MODEL_LOADED_VERSION = None


class FakeModelStore:
    def __init__(self, model_bytes: bytes, config: dict, version: str = "v1"):
        self.model_bytes = model_bytes
        self.model_config = config
        self.version = version
        self.prefix = "quality-classifier"
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


def _config(labels=("other", "genuinely_uplifting_and_substantive"), threshold=0.39):
    return {"labels": list(labels), "threshold": threshold}


def test_score_batch_empty_posts_returns_empty_dict():
    assert quality_model.score_batch([]) == {}


def test_score_batch_returns_empty_dict_when_r2_unconfigured():
    posts = [FakePost(id=uuid4(), text="a local shelter found homes for 40 rescue dogs this weekend")]
    assert quality_model.score_batch(posts) == {}
    assert quality_model.QUALITY_METHOD is None


def test_load_model_success_sets_method_and_version(fixture_quality_onnx_bytes):
    store = FakeModelStore(fixture_quality_onnx_bytes, _config(), version="v3")
    quality_model.load_model(store)
    assert quality_model.QUALITY_METHOD == "tfidf_lr_v1"
    assert quality_model.QUALITY_MODEL_LOADED_VERSION == "v3"


def test_load_model_failure_leaves_method_unset():
    quality_model.load_model(FailingModelStore())
    assert quality_model.QUALITY_METHOD is None
    posts = [FakePost(id=uuid4(), text="a local shelter found homes for 40 rescue dogs this weekend")]
    assert quality_model.score_batch(posts) == {}


def test_load_model_rejects_label_order_mismatch(fixture_quality_onnx_bytes):
    # config.json claims 3 labels but the model only outputs 2 -- the
    # silent-wrong-answer failure mode this check exists to catch.
    store = FakeModelStore(
        fixture_quality_onnx_bytes, _config(labels=("other", "genuinely_uplifting_and_substantive", "extra"))
    )
    quality_model.load_model(store)
    assert quality_model.QUALITY_METHOD is None


def test_load_model_rejects_config_missing_quality_label(fixture_quality_onnx_bytes):
    # A config.json that doesn't even have the positive label in its labels
    # list -- labels.index() raises, caught by the same broad except as any
    # other load failure.
    store = FakeModelStore(fixture_quality_onnx_bytes, _config(labels=("yes", "no")))
    quality_model.load_model(store)
    assert quality_model.QUALITY_METHOD is None


def test_score_batch_uses_trained_model_after_successful_load(fixture_quality_onnx_bytes):
    store = FakeModelStore(fixture_quality_onnx_bytes, _config())
    quality_model.load_model(store)

    posts = [
        FakePost(id=uuid4(), text="a local shelter found homes for 40 rescue dogs this weekend"),
        FakePost(id=uuid4(), text="happy friday everyone"),
    ]
    results = quality_model.score_batch(posts)

    assert set(results) == {post.id for post in posts}
    assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in results.values())
    # Not asserting which side of the threshold each lands on -- a handful
    # of trivial training examples doesn't guarantee a stable decision
    # boundary, only that scoring plumbing (label index, batch shape) is
    # wired correctly.


def test_score_batch_lazy_loads_once(monkeypatch, fixture_quality_onnx_bytes):
    store = FakeModelStore(fixture_quality_onnx_bytes, _config())
    construct_count = {"n": 0}

    def fake_construct(prefix):
        assert prefix == "quality-classifier"
        construct_count["n"] += 1
        return store

    monkeypatch.setattr(quality_model.config, "r2_configured", lambda: True)
    monkeypatch.setattr(quality_model.model_store, "R2ModelStore", fake_construct)

    posts = [FakePost(id=uuid4(), text="a local shelter found homes for 40 rescue dogs this weekend")]
    quality_model.score_batch(posts)
    quality_model.score_batch(posts)

    assert construct_count["n"] == 1
    assert quality_model.QUALITY_METHOD == "tfidf_lr_v1"


def test_load_model_uses_env_override_without_hitting_r2(fixture_quality_onnx_bytes):
    store = FakeModelStore(fixture_quality_onnx_bytes, _config(), version="v1")
    original = quality_model.config.QUALITY_MODEL_VERSION
    quality_model.config.QUALITY_MODEL_VERSION = "v7-pinned"
    try:
        quality_model.load_model(store)
    finally:
        quality_model.config.QUALITY_MODEL_VERSION = original

    assert store.resolve_version_calls == 0
    assert quality_model.QUALITY_METHOD == "tfidf_lr_v1"
    assert all("v7-pinned" in key for key in store.requested_keys)
