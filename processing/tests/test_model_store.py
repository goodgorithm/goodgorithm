import json

import pytest

import config
import model_store


class FakeBody:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakeS3Client:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.requested_keys: list[str] = []

    def get_object(self, Bucket, Key):
        self.requested_keys.append(Key)
        return {"Body": FakeBody(self.objects[Key])}


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "test-account")
    monkeypatch.setattr(config, "R2_ACCESS_KEY_ID", "test-key")
    monkeypatch.setattr(config, "R2_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "test-bucket")
    return model_store.R2ModelStore(prefix="sentiment-cnn")


def test_resolve_version_reads_latest_json(store):
    fake = FakeS3Client({"sentiment-cnn/latest.json": json.dumps({"version": "v3"}).encode()})
    store.client = fake
    assert store.resolve_version() == "v3"
    assert fake.requested_keys == ["sentiment-cnn/latest.json"]


def test_fetch_reads_model_vocab_and_config(store):
    fake = FakeS3Client(
        {
            "sentiment-cnn/v2/model.onnx": b"fake-onnx-bytes",
            "sentiment-cnn/v2/vocab.json": json.dumps({"<pad>": 0, "hello": 1}).encode(),
            "sentiment-cnn/v2/config.json": json.dumps({"embedding_dim": 100}).encode(),
        }
    )
    store.client = fake

    model_bytes, vocab, model_config = store.fetch("v2")

    assert model_bytes == b"fake-onnx-bytes"
    assert vocab == {"<pad>": 0, "hello": 1}
    assert model_config == {"embedding_dim": 100}


def test_get_bytes_and_get_json_work_with_any_prefix(monkeypatch):
    # category_model.py uses these two directly (no vocab file, so fetch()
    # doesn't fit) - confirm they're usable standalone with a different
    # prefix, not just through fetch()'s sentiment-shaped bundling.
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "test-account")
    monkeypatch.setattr(config, "R2_ACCESS_KEY_ID", "test-key")
    monkeypatch.setattr(config, "R2_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "test-bucket")
    category_store = model_store.R2ModelStore(prefix="category-classifier")
    fake = FakeS3Client(
        {
            "category-classifier/v1/model.onnx": b"fake-onnx-bytes",
            "category-classifier/v1/config.json": json.dumps({"labels": ["sports"]}).encode(),
        }
    )
    category_store.client = fake

    assert category_store.get_bytes("category-classifier/v1/model.onnx") == b"fake-onnx-bytes"
    assert category_store.get_json("category-classifier/v1/config.json") == {"labels": ["sports"]}
