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
    deterministic, known model."""
    _vocab_size, num_classes = prob_table.shape

    input_ids = helper.make_tensor_value_info("input_ids", TensorProto.INT64, [1, None])
    probs = helper.make_tensor_value_info("probs", TensorProto.FLOAT, [1, num_classes])

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
