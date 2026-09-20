from pipeline_stages import aggregator_demote, penalties

FLIPBOARD = frozenset({"flipboard.com", "flipboard.social"})

_PENALTY_NAMES = ("aggregator",)


def _ctx(**overrides):
    base = dict(
        source="bluesky",
        author_id="did:plc:someone",
        aggregator_instances=frozenset(),
    )
    base.update(overrides)
    return penalties.PenaltyContext(**base)


def test_registry_names():
    assert tuple(p.name for p in penalties.PENALTIES) == _PENALTY_NAMES


def test_apply_no_penalties_is_identity():
    result = penalties.apply(_ctx())
    assert result.multiplier == 1.0
    assert result.detail == {name: 1.0 for name in _PENALTY_NAMES}


def test_apply_reads_the_aggregator_instance_list():
    result = penalties.apply(
        _ctx(source="mastodon", author_id="hachyderm.io/x@flipboard.com", aggregator_instances=FLIPBOARD)
    )
    assert result.detail["aggregator"] == aggregator_demote.AGGREGATOR_DEMOTE_MULTIPLIER
    assert result.multiplier == aggregator_demote.AGGREGATOR_DEMOTE_MULTIPLIER


def test_apply_multiplier_equals_product_of_numeric_detail():
    result = penalties.apply(
        _ctx(source="mastodon", author_id="flipboard.com/mag", aggregator_instances=FLIPBOARD)
    )
    product = 1.0
    for name in _PENALTY_NAMES:
        product *= result.detail[name]
    assert abs(result.multiplier - product) < 1e-9
