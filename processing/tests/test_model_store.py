import json

import pytest

import config
from infra import model_store


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
    monkeypatch.setattr(config, "R2_MODELS_ACCOUNT_ID", "test-account")
    monkeypatch.setattr(config, "R2_MODELS_ACCESS_KEY_ID", "test-key")
    monkeypatch.setattr(config, "R2_MODELS_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setattr(config, "R2_MODELS_BUCKET_NAME", "test-bucket")
    return model_store.R2ModelStore(prefix="political-classifier")


def test_resolve_version_reads_latest_json(store):
    fake = FakeS3Client({"political-classifier/latest.json": json.dumps({"version": "v3"}).encode()})
    store.client = fake
    assert store.resolve_version() == "v3"
    assert fake.requested_keys == ["political-classifier/latest.json"]


def test_get_bytes_and_get_json_work_with_any_prefix(monkeypatch):
    monkeypatch.setattr(config, "R2_MODELS_ACCOUNT_ID", "test-account")
    monkeypatch.setattr(config, "R2_MODELS_ACCESS_KEY_ID", "test-key")
    monkeypatch.setattr(config, "R2_MODELS_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setattr(config, "R2_MODELS_BUCKET_NAME", "test-bucket")
    quality_store = model_store.R2ModelStore(prefix="quality-classifier")
    fake = FakeS3Client(
        {
            "quality-classifier/v1/model.onnx": b"fake-onnx-bytes",
            "quality-classifier/v1/config.json": json.dumps({"labels": ["genuinely_uplifting_and_substantive"]}).encode(),
        }
    )
    quality_store.client = fake

    assert quality_store.get_bytes("quality-classifier/v1/model.onnx") == b"fake-onnx-bytes"
    assert quality_store.get_json("quality-classifier/v1/config.json") == {"labels": ["genuinely_uplifting_and_substantive"]}
