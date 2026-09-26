import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "fetch_local_models", Path(__file__).resolve().parent.parent / "scripts" / "fetch_local_models.py"
)
fetch_local_models = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch_local_models)


def _release(tag):
    return {"tag_name": tag, "assets": []}


RELEASES = [
    _release("quality-classifier-v1"),
    _release("quality-classifier-v10"),
    _release("quality-classifier-v2"),
    _release("political-classifier-v1"),
    _release("political-centroid-v1"),
    _release("sentiment-cnn-v4"),
]


def test_selects_highest_version_numerically_not_lexically():
    release = fetch_local_models.select_release(RELEASES, "quality-classifier", None)
    assert release["tag_name"] == "quality-classifier-v10"


def test_prefix_match_is_exact():
    # "political-classifier" must not pick up "political-centroid" releases, or vice versa
    assert fetch_local_models.select_release(RELEASES, "political-classifier", None)["tag_name"] == "political-classifier-v1"
    assert fetch_local_models.select_release(RELEASES, "political-centroid", None)["tag_name"] == "political-centroid-v1"


def test_pinned_version_is_honored():
    release = fetch_local_models.select_release(RELEASES, "quality-classifier", "v2")
    assert release["tag_name"] == "quality-classifier-v2"
    assert fetch_local_models.version_of(release, "quality-classifier") == "v2"


def test_missing_pinned_version_exits():
    with pytest.raises(SystemExit):
        fetch_local_models.select_release(RELEASES, "quality-classifier", "v99")


def test_no_releases_for_prefix_exits():
    with pytest.raises(SystemExit):
        fetch_local_models.select_release([_release("sentiment-cnn-v4")], "quality-classifier", None)


def test_parse_pins_validates_shape():
    assert fetch_local_models.parse_pins(["quality-classifier=v3"]) == {"quality-classifier": "v3"}
    for bad in ["quality-classifier", "unknown-model=v1", "quality-classifier=3"]:
        with pytest.raises(SystemExit):
            fetch_local_models.parse_pins([bad])
