from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from pipeline_stages import category_model


@dataclass
class FakePost:
    id: UUID
    text: str


@dataclass
class FakeTopicalityResult:
    entities: list[str]
    top_terms: list[str]


@pytest.fixture(autouse=True)
def reset_category_module_state(monkeypatch):
    """category_model.py has module-global mutable state (the loaded
    session, labels, threshold, load-attempted flag, CATEGORY_METHOD) so
    tests don't bleed into each other regardless of run order. Also forces
    r2_configured() False by default so tests are hermetic regardless of
    what's in a developer's local .env — tests that want the classifier
    path override this themselves."""
    category_model._session = None
    category_model._labels = None
    category_model._threshold = 0.0
    category_model._load_attempted = False
    category_model.CATEGORY_METHOD = "keyword_v1"
    monkeypatch.setattr(category_model.config, "r2_configured", lambda: False)
    yield
    category_model._session = None
    category_model._labels = None
    category_model._threshold = 0.0
    category_model._load_attempted = False
    category_model.CATEGORY_METHOD = "keyword_v1"


class FakeModelStore:
    def __init__(self, model_bytes: bytes, config: dict, version: str = "v1"):
        self.model_bytes = model_bytes
        self.model_config = config
        self.version = version
        self.prefix = "category-classifier"
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


def _config(labels=("sports", "food_dining"), threshold=0.5):
    return {"labels": list(labels), "confidence_threshold": threshold}


def test_categorize_uses_keyword_fallback_when_r2_unconfigured():
    category = category_model.categorize("Just qualified for the biggest esports tournament ever!", ["esports"], [])
    assert category == "gaming"
    assert category_model.CATEGORY_METHOD == "keyword_v1"


def test_categorize_returns_none_when_nothing_matches_and_no_model():
    category = category_model.categorize("a totally generic political post", ["trump"], ["election"])
    assert category is None
    assert category_model.CATEGORY_METHOD == "keyword_v1"


def test_load_model_success_switches_method_to_trained_classifier(fixture_category_onnx_bytes):
    store = FakeModelStore(fixture_category_onnx_bytes, _config())
    category_model.load_model(store)
    assert category_model.CATEGORY_METHOD == "tfidf_lr_v1"


def test_categorize_uses_trained_model_after_successful_load(fixture_category_onnx_bytes):
    store = FakeModelStore(fixture_category_onnx_bytes, _config(threshold=0.0))
    category_model.load_model(store)
    category = category_model.categorize("the team won the championship game", [], [])
    assert category == "sports"


def test_categorize_abstains_below_confidence_threshold(fixture_category_onnx_bytes):
    # A very high threshold makes the model abstain on everything - proves
    # the threshold is actually enforced, not just carried around unused.
    store = FakeModelStore(fixture_category_onnx_bytes, _config(threshold=0.99))
    category_model.load_model(store)
    category = category_model.categorize("the team won the championship game", [], [])
    assert category is None


def test_load_model_failure_falls_back_to_keyword_matcher():
    category_model.load_model(FailingModelStore())
    assert category_model.CATEGORY_METHOD == "keyword_v1"
    category = category_model.categorize("Just qualified for the biggest esports tournament ever!", ["esports"], [])
    assert category == "gaming"


def test_load_model_rejects_label_order_mismatch(fixture_category_onnx_bytes):
    # config.json claims 3 labels but the model only outputs 2 - the
    # silent-wrong-answer failure mode this check exists to catch.
    store = FakeModelStore(fixture_category_onnx_bytes, _config(labels=("sports", "food_dining", "gaming")))
    category_model.load_model(store)
    assert category_model.CATEGORY_METHOD == "keyword_v1"


def test_categorize_lazy_loads_once(monkeypatch, fixture_category_onnx_bytes):
    store = FakeModelStore(fixture_category_onnx_bytes, _config())
    construct_count = {"n": 0}

    def fake_construct(prefix):
        assert prefix == "category-classifier"
        construct_count["n"] += 1
        return store

    monkeypatch.setattr(category_model.config, "r2_configured", lambda: True)
    monkeypatch.setattr(category_model.model_store, "R2ModelStore", fake_construct)

    category_model.categorize("the team won the championship game", [], [])
    category_model.categorize("the team won the championship game", [], [])

    assert construct_count["n"] == 1
    assert category_model.CATEGORY_METHOD == "tfidf_lr_v1"


def test_load_model_uses_env_override_without_hitting_r2(fixture_category_onnx_bytes):
    store = FakeModelStore(fixture_category_onnx_bytes, _config(), version="v1")
    original = category_model.config.CATEGORY_MODEL_VERSION
    category_model.config.CATEGORY_MODEL_VERSION = "v7-pinned"
    try:
        category_model.load_model(store)
    finally:
        category_model.config.CATEGORY_MODEL_VERSION = original

    assert store.resolve_version_calls == 0
    assert category_model.CATEGORY_METHOD == "tfidf_lr_v1"
    assert all("v7-pinned" in key for key in store.requested_keys)


def test_categorize_batch_empty_returns_empty_dict():
    assert category_model.categorize_batch([], {}) == {}


def test_categorize_batch_matches_per_post_categorize_with_keyword_fallback():
    posts = [
        FakePost(id=uuid4(), text="Just qualified for the biggest esports tournament ever!"),
        FakePost(id=uuid4(), text="a totally generic political post"),
    ]
    topicality_results = {
        posts[0].id: FakeTopicalityResult(entities=["esports"], top_terms=[]),
        posts[1].id: FakeTopicalityResult(entities=["trump"], top_terms=["election"]),
    }

    results = category_model.categorize_batch(posts, topicality_results)

    assert results[posts[0].id] == "gaming"
    assert results[posts[1].id] is None
    assert category_model.CATEGORY_METHOD == "keyword_v1"


def test_categorize_batch_uses_trained_model_after_successful_load(fixture_category_onnx_bytes):
    store = FakeModelStore(fixture_category_onnx_bytes, _config(threshold=0.0))
    category_model.load_model(store)

    posts = [
        FakePost(id=uuid4(), text="the team won the championship game"),
        FakePost(id=uuid4(), text="tried a new restaurant for dinner"),
    ]
    # Fallback-only data -- the model path ignores this, proving results
    # come from the batched ONNX call, not a silent taxonomy fallback.
    topicality_results = {post.id: FakeTopicalityResult(entities=[], top_terms=[]) for post in posts}

    results = category_model.categorize_batch(posts, topicality_results)

    assert results[posts[0].id] == "sports"
    assert results[posts[1].id] == "food_dining"


def test_categorize_batch_matches_single_post_categorize_call_for_call(fixture_category_onnx_bytes):
    # The batched ONNX call must produce identical per-post results to the
    # single-post path -- proves batching is a pure performance change.
    store = FakeModelStore(fixture_category_onnx_bytes, _config(threshold=0.0))
    category_model.load_model(store)

    texts = [
        "the team won the championship game",
        "tried a new restaurant for dinner",
        "our team scored a goal in the match",
    ]
    posts = [FakePost(id=uuid4(), text=text) for text in texts]
    topicality_results = {post.id: FakeTopicalityResult(entities=[], top_terms=[]) for post in posts}

    batch_results = category_model.categorize_batch(posts, topicality_results)
    individual_results = {post.id: category_model.categorize(post.text, [], []) for post in posts}

    assert batch_results == individual_results
