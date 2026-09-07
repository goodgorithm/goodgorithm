from uuid import uuid4

from pipeline_stages import aggregator_demote, penalties
from pipeline_stages.context_dependency import ContextClassification

# a structured "now playing on <station>" post -- triggers the shape penalty
NOWPLAYING = "▶️ #NowPlaying on Hot 21 Radio: 93 'Til Infinity by Souls of Mischief \U0001f525 Tune in now: https://www.hot21radio.com #Hot21Radio"

FLIPBOARD = frozenset({"flipboard.com", "flipboard.social"})


def _ctx(**overrides):
    base = dict(
        source="bluesky",
        author_id=f"did:plc:{uuid4().hex}",
        raw_json={},
        text="a plain post about a walk in the park",
        context_action=ContextClassification(action="none"),
        aggregator_instances=frozenset(),
        shape_config={},
    )
    base.update(overrides)
    return penalties.PenaltyContext(**base)


def test_registry_names_are_the_four_penalties():
    assert tuple(p.name for p in penalties.PENALTIES) == ("context", "link_share", "aggregator", "shape")


def test_apply_no_penalties_is_identity():
    result = penalties.apply(_ctx())
    assert result.multiplier == 1.0
    assert result.detail == {
        "context": 1.0,
        "link_share": 1.0,
        "aggregator": 1.0,
        "shape": 1.0,
        "shape_name": None,
    }


def test_apply_multiplies_every_penalty_and_records_the_breakdown():
    result = penalties.apply(
        _ctx(
            text=NOWPLAYING,
            context_action=ContextClassification(action="devalue", devalue_multiplier=0.4),
        )
    )
    assert result.detail["context"] == 0.4
    assert result.detail["shape"] == 0.3
    assert result.detail["shape_name"] == "nowplaying"
    assert result.detail["link_share"] == 1.0
    assert result.detail["aggregator"] == 1.0
    # multiplier is the product of the numeric detail entries
    assert abs(result.multiplier - (0.4 * 1.0 * 1.0 * 0.3)) < 1e-9


def test_apply_reads_the_aggregator_instance_list():
    result = penalties.apply(
        _ctx(source="mastodon", author_id="hachyderm.io/x@flipboard.com", aggregator_instances=FLIPBOARD)
    )
    assert result.detail["aggregator"] == aggregator_demote.AGGREGATOR_DEMOTE_MULTIPLIER
    assert result.multiplier == aggregator_demote.AGGREGATOR_DEMOTE_MULTIPLIER


def test_apply_multiplier_equals_product_of_numeric_detail():
    result = penalties.apply(
        _ctx(
            source="mastodon",
            author_id="flipboard.com/mag",
            aggregator_instances=FLIPBOARD,
            text=NOWPLAYING,
            context_action=ContextClassification(action="devalue", devalue_multiplier=0.4),
        )
    )
    product = 1.0
    for name in ("context", "link_share", "aggregator", "shape"):
        product *= result.detail[name]
    assert abs(result.multiplier - product) < 1e-9
