from dataclasses import dataclass
from uuid import UUID, uuid4

import numpy as np
import pytest

from pipeline_stages import political_centroid


@dataclass
class FakePost:
    id: UUID
    text: str


class FakeKeyedVectors:
    """A tiny stand-in for gensim's KeyedVectors -- dict-like word -> vector
    lookup, no real embeddings download."""

    def __init__(self, vectors: dict):
        self._vectors = {k: np.array(v, dtype=np.float32) for k, v in vectors.items()}

    def __contains__(self, word):
        return word in self._vectors

    def __getitem__(self, word):
        return self._vectors[word]


@pytest.fixture(autouse=True)
def reset_political_centroid_module_state(monkeypatch):
    """political_centroid.py has module-global mutable state (the loaded
    embeddings, the two centroid vectors, load-attempted flag,
    POLITICAL_CENTROID_METHOD) so tests don't bleed into each other
    regardless of run order. Mirrors test_political_model.py's equivalent
    fixture."""
    political_centroid._embeddings = None
    political_centroid._political_centroid = None
    political_centroid._non_political_centroid = None
    political_centroid._load_attempted = False
    political_centroid.POLITICAL_CENTROID_METHOD = None
    political_centroid.POLITICAL_CENTROID_MODEL_LOADED_VERSION = None
    monkeypatch.setattr(political_centroid.config, "r2_configured", lambda: False)
    yield
    political_centroid._embeddings = None
    political_centroid._political_centroid = None
    political_centroid._non_political_centroid = None
    political_centroid._load_attempted = False
    political_centroid.POLITICAL_CENTROID_METHOD = None
    political_centroid.POLITICAL_CENTROID_MODEL_LOADED_VERSION = None


class FakeModelStore:
    def __init__(self, centroid_config: dict, version: str = "v1"):
        self.centroid_config = centroid_config
        self.version = version
        self.prefix = "political-centroid"
        self.resolve_version_calls = 0
        self.requested_keys: list[str] = []

    def resolve_version(self) -> str:
        self.resolve_version_calls += 1
        return self.version

    def get_json(self, key: str) -> dict:
        self.requested_keys.append(key)
        assert key.startswith(self.prefix) and key.endswith("/centroids.json")
        return self.centroid_config


class FailingModelStore:
    def resolve_version(self) -> str:
        raise RuntimeError("simulated R2 outage")


FAKE_VOCAB = {
    "senate": [1.0, 0.0],
    "bill": [0.9, 0.1],
    "walk": [0.0, 1.0],
    "park": [0.1, 0.9],
}


def _centroid_config():
    return {
        "embedding": "glove-fake",
        "political_centroid": [1.0, 0.0],
        "non_political_centroid": [0.0, 1.0],
    }


def _patch_gensim(monkeypatch, vocab=FAKE_VOCAB):
    monkeypatch.setattr(political_centroid.gensim_api, "load", lambda name: FakeKeyedVectors(vocab))


def test_score_batch_empty_posts_returns_empty_dict():
    assert political_centroid.score_batch([]) == {}


def test_score_batch_returns_empty_dict_when_r2_unconfigured():
    posts = [FakePost(id=uuid4(), text="the senate voted on the new bill")]
    assert political_centroid.score_batch(posts) == {}
    assert political_centroid.POLITICAL_CENTROID_METHOD is None


def test_load_model_success_sets_method_and_version(monkeypatch):
    _patch_gensim(monkeypatch)
    store = FakeModelStore(_centroid_config(), version="v3")
    political_centroid.load_model(store)
    assert political_centroid.POLITICAL_CENTROID_METHOD == "nearest_centroid_v1"
    assert political_centroid.POLITICAL_CENTROID_MODEL_LOADED_VERSION == "v3"


def test_load_model_failure_leaves_method_unset():
    political_centroid.load_model(FailingModelStore())
    assert political_centroid.POLITICAL_CENTROID_METHOD is None
    posts = [FakePost(id=uuid4(), text="the senate voted on the new bill")]
    assert political_centroid.score_batch(posts) == {}


def test_load_model_failure_when_embeddings_download_raises(monkeypatch):
    def raise_load(name):
        raise RuntimeError("simulated download failure")

    monkeypatch.setattr(political_centroid.gensim_api, "load", raise_load)
    store = FakeModelStore(_centroid_config())
    political_centroid.load_model(store)
    assert political_centroid.POLITICAL_CENTROID_METHOD is None


def test_score_batch_scores_toward_the_closer_centroid(monkeypatch):
    _patch_gensim(monkeypatch)
    store = FakeModelStore(_centroid_config())
    political_centroid.load_model(store)

    posts = [
        FakePost(id=uuid4(), text="senate bill"),
        FakePost(id=uuid4(), text="walk park"),
    ]
    results = political_centroid.score_batch(posts)

    assert results[posts[0].id] > 0  # closer to the political centroid [1, 0]
    assert results[posts[1].id] < 0  # closer to the non-political centroid [0, 1]


def test_score_batch_unknown_words_score_zero(monkeypatch):
    _patch_gensim(monkeypatch)
    store = FakeModelStore(_centroid_config())
    political_centroid.load_model(store)

    posts = [FakePost(id=uuid4(), text="zzz unknown words only")]
    results = political_centroid.score_batch(posts)
    assert results[posts[0].id] == 0.0


def test_score_batch_lazy_loads_once(monkeypatch):
    _patch_gensim(monkeypatch)
    store = FakeModelStore(_centroid_config())
    construct_count = {"n": 0}

    def fake_construct(prefix):
        assert prefix == "political-centroid"
        construct_count["n"] += 1
        return store

    monkeypatch.setattr(political_centroid.config, "r2_configured", lambda: True)
    monkeypatch.setattr(political_centroid.model_store, "R2ModelStore", fake_construct)

    posts = [FakePost(id=uuid4(), text="senate bill")]
    political_centroid.score_batch(posts)
    political_centroid.score_batch(posts)

    assert construct_count["n"] == 1
    assert political_centroid.POLITICAL_CENTROID_METHOD == "nearest_centroid_v1"


def test_load_model_uses_env_override_without_hitting_r2(monkeypatch):
    _patch_gensim(monkeypatch)
    store = FakeModelStore(_centroid_config(), version="v1")
    original = political_centroid.config.POLITICAL_CENTROID_MODEL_VERSION
    political_centroid.config.POLITICAL_CENTROID_MODEL_VERSION = "v7-pinned"
    try:
        political_centroid.load_model(store)
    finally:
        political_centroid.config.POLITICAL_CENTROID_MODEL_VERSION = original

    assert store.resolve_version_calls == 0
    assert political_centroid.POLITICAL_CENTROID_METHOD == "nearest_centroid_v1"
    assert all("v7-pinned" in key for key in store.requested_keys)
