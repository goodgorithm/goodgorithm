import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper


def _build_fixture_graph(prob_table: np.ndarray) -> bytes:
    """A tiny ONNX graph matching the real sentiment model's
    input_ids -> probs I/O contract: Gather into a hardcoded per-token-id
    probability table, keyed by the first token id. No torch needed to
    build or run this — exercises sentiment.py's real plumbing (session
    creation, tensor shapes, score conversion) against a fully
    deterministic, known model. Dynamic batch dim on both input_ids and
    probs, matching the real model's dynamic_axes export (issue #52) —
    exercises score_sentiment_batch()'s multi-row calls, not just batch=1."""
    _vocab_size, num_classes = prob_table.shape

    input_ids = helper.make_tensor_value_info("input_ids", TensorProto.INT64, [None, None])
    probs = helper.make_tensor_value_info("probs", TensorProto.FLOAT, [None, num_classes])

    table_init = helper.make_tensor(
        "prob_table", TensorProto.FLOAT, prob_table.shape, prob_table.flatten().tolist()
    )
    starts = helper.make_tensor("starts", TensorProto.INT64, [1], [0])
    ends = helper.make_tensor("ends", TensorProto.INT64, [1], [1])
    axes = helper.make_tensor("axes", TensorProto.INT64, [1], [1])
    squeeze_axes = helper.make_tensor("squeeze_axes", TensorProto.INT64, [1], [1])

    slice_node = helper.make_node("Slice", ["input_ids", "starts", "ends", "axes"], ["first_token_2d"])
    squeeze_node = helper.make_node("Squeeze", ["first_token_2d", "squeeze_axes"], ["first_token"])
    gather_node = helper.make_node("Gather", ["prob_table", "first_token"], ["probs"], axis=0)

    graph = helper.make_graph(
        [slice_node, squeeze_node, gather_node],
        "fixture",
        [input_ids],
        [probs],
        initializer=[table_init, starts, ends, axes, squeeze_axes],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    onnx.checker.check_model(model)
    return model.SerializeToString()


@pytest.fixture
def fixture_onnx_bytes() -> bytes:
    # token id 0 -> negative-leaning, 1 -> positive-leaning, 2 -> neutral-leaning
    prob_table = np.array(
        [
            [0.7, 0.2, 0.1],
            [0.1, 0.2, 0.7],
            [0.2, 0.6, 0.2],
        ],
        dtype=np.float32,
    )
    return _build_fixture_graph(prob_table)


@pytest.fixture
def fixture_vocab() -> dict:
    return {"<pad>": 0, "<unk>": 0, "goodword": 1, "okword": 2}


@pytest.fixture
def fixture_onnx_bytes_wrong_width() -> bytes:
    """Same shape as fixture_onnx_bytes but with 2 output classes instead
    of 3 -- exercises sentiment.py's load-time width-check smoke test
    (issue #74), mirroring fixture_category_onnx_bytes's sibling use for
    category_model.py's own label-order-mismatch test."""
    prob_table = np.array(
        [
            [0.7, 0.3],
            [0.1, 0.9],
        ],
        dtype=np.float32,
    )
    return _build_fixture_graph(prob_table)


@pytest.fixture
def fixture_category_onnx_bytes() -> bytes:
    """A real, tiny TF-IDF + one-vs-rest LogisticRegression pipeline,
    trained on trivial synthetic data and exported via skl2onnx exactly
    like the real training notebook — not a hand-built ONNX graph like
    fixture_onnx_bytes above, since string-keyed lookup has no simple
    built-in ONNX primitive the way int64 token-id Gather does. This
    exercises the real conversion path, not an approximation of it."""
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.multiclass import OneVsRestClassifier
    from sklearn.pipeline import Pipeline
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import StringTensorType

    texts = [
        "the team won the championship game",
        "our team scored a goal in the match",
        "new recipe for homemade pasta tonight",
        "tried a new restaurant for dinner",
    ] * 5
    labels = np.array(
        [[1, 0], [1, 0], [0, 1], [0, 1]] * 5,
        dtype=int,
    )

    vectorizer = TfidfVectorizer()
    clf = OneVsRestClassifier(LogisticRegression(max_iter=1000))
    pipeline = Pipeline([("tfidf", vectorizer), ("clf", clf)])
    pipeline.fit(texts, labels)

    onnx_model = convert_sklearn(
        pipeline,
        initial_types=[("input", StringTensorType([None, 1]))],
        options={id(clf): {"zipmap": False}},
    )
    return onnx_model.SerializeToString()
