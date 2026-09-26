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


def _local_layout(root, prefix="quality-classifier", version="v2"):
    version_dir = root / prefix / version
    version_dir.mkdir(parents=True)
    (version_dir / "model.onnx").write_bytes(b"local-onnx-bytes")
    (version_dir / "config.json").write_text(json.dumps({"labels": ["other", "good"]}))
    (root / prefix / "latest.json").write_text(json.dumps({"version": version}))


def test_local_dir_store_mirrors_the_r2_layout(tmp_path):
    _local_layout(tmp_path)
    store = model_store.LocalDirModelStore(str(tmp_path), "quality-classifier")

    assert store.resolve_version() == "v2"
    assert store.get_bytes("quality-classifier/v2/model.onnx") == b"local-onnx-bytes"
    assert store.get_json("quality-classifier/v2/config.json") == {"labels": ["other", "good"]}


def test_local_dir_store_missing_artifact_raises(tmp_path):
    store = model_store.LocalDirModelStore(str(tmp_path), "quality-classifier")
    with pytest.raises(FileNotFoundError):
        store.resolve_version()


def _clear_r2(monkeypatch):
    for name in ("R2_MODELS_ACCOUNT_ID", "R2_MODELS_ACCESS_KEY_ID", "R2_MODELS_SECRET_ACCESS_KEY", "R2_MODELS_BUCKET_NAME"):
        monkeypatch.setattr(config, name, None)


def _set_r2(monkeypatch):
    monkeypatch.setattr(config, "R2_MODELS_ACCOUNT_ID", "test-account")
    monkeypatch.setattr(config, "R2_MODELS_ACCESS_KEY_ID", "test-key")
    monkeypatch.setattr(config, "R2_MODELS_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setattr(config, "R2_MODELS_BUCKET_NAME", "test-bucket")


def test_default_store_local_only(monkeypatch, tmp_path):
    _clear_r2(monkeypatch)
    monkeypatch.setattr(config, "LOCAL_MODELS_DIR", str(tmp_path))
    store = model_store.default_store("quality-classifier")
    assert isinstance(store, model_store.LocalDirModelStore)
    assert store.prefix == "quality-classifier"
    assert config.models_source() == "local"


def test_default_store_r2_only(monkeypatch):
    _set_r2(monkeypatch)
    store = model_store.default_store("political-classifier")
    assert isinstance(store, model_store.R2ModelStore)
    assert store.prefix == "political-classifier"
    assert config.models_source() == "r2"


def test_default_store_none_configured(monkeypatch):
    _clear_r2(monkeypatch)
    assert model_store.default_store("quality-classifier") is None
    assert config.models_source() is None


def test_default_store_refuses_both_sources(monkeypatch, tmp_path):
    _set_r2(monkeypatch)
    monkeypatch.setattr(config, "LOCAL_MODELS_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        model_store.default_store("quality-classifier")


def test_validate_exits_when_local_dir_and_any_r2_var_are_set(monkeypatch, tmp_path, capsys):
    _clear_r2(monkeypatch)
    monkeypatch.setattr(config, "_REQUIRED", {})
    monkeypatch.setattr(config, "LOCAL_MODELS_DIR", str(tmp_path))
    # a single, half-configured R2 var is enough to conflict
    monkeypatch.setattr(config, "R2_MODELS_BUCKET_NAME", "test-bucket")
    with pytest.raises(SystemExit) as exc:
        config.validate()
    assert exc.value.code == 1
    assert "LOCAL_MODELS_DIR and R2_MODELS_* are both set" in capsys.readouterr().err


def test_validate_passes_with_either_source_alone(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_REQUIRED", {})
    _clear_r2(monkeypatch)
    monkeypatch.setattr(config, "LOCAL_MODELS_DIR", str(tmp_path))
    config.validate()
    monkeypatch.setattr(config, "LOCAL_MODELS_DIR", None)
    _set_r2(monkeypatch)
    config.validate()
