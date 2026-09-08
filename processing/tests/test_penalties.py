from uuid import uuid4

from pipeline_stages import aggregator_demote, penalties
from pipeline_stages.context_dependency import ContextClassification

# a structured "now playing on <station>" post -- triggers the shape penalty
NOWPLAYING = "▶️ #NowPlaying on Hot 21 Radio: 93 'Til Infinity by Souls of Mischief \U0001f525 Tune in now: https://www.hot21radio.com #Hot21Radio"

# a directory-submission CTA -- triggers the shape penalty via the "promo" shape
PROMO = "Puzzler is featured on Awesome Indie! Upvote it → https://awesomeindie.com/p/puzzler"

FLIPBOARD = frozenset({"flipboard.com", "flipboard.social"})
SHORTENERS = frozenset({"dlvr.it", "ift.tt"})

_PENALTY_NAMES = ("context", "link_share", "aggregator", "syndication", "shape")


def _ctx(**overrides):
    base = dict(
        source="bluesky",
        author_id=f"did:plc:{uuid4().hex}",
        raw_json={},
        text="a plain post about a walk in the park",
        context_action=ContextClassification(action="none"),
        aggregator_instances=frozenset(),
        syndication_domains=frozenset(),
        shape_config={},
    )
    base.update(overrides)
    return penalties.PenaltyContext(**base)


def test_registry_names():
    assert tuple(p.name for p in penalties.PENALTIES) == _PENALTY_NAMES


def test_apply_no_penalties_is_identity():
    result = penalties.apply(_ctx())
    assert result.multiplier == 1.0
    assert result.detail == {name: 1.0 for name in _PENALTY_NAMES} | {"shape_name": None}


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
    assert result.detail["syndication"] == 1.0
    assert abs(result.multiplier - (0.4 * 0.3)) < 1e-9


def test_apply_records_the_promo_shape():
    result = penalties.apply(_ctx(text=PROMO))
    assert result.detail["shape"] == 0.35
    assert result.detail["shape_name"] == "promo"
    assert abs(result.multiplier - 0.35) < 1e-9


def test_apply_reads_the_aggregator_instance_list():
    result = penalties.apply(
        _ctx(source="mastodon", author_id="hachyderm.io/x@flipboard.com", aggregator_instances=FLIPBOARD)
    )
    assert result.detail["aggregator"] == aggregator_demote.AGGREGATOR_DEMOTE_MULTIPLIER
    assert result.multiplier == aggregator_demote.AGGREGATOR_DEMOTE_MULTIPLIER


def test_apply_syndication_matches_a_shortener_link_on_either_platform():
    for source in ("bluesky", "mastodon"):
        result = penalties.apply(
            _ctx(source=source, text="Sicily, Italy http://dlvr.it/TVMgSf #Photography", syndication_domains=SHORTENERS)
        )
        assert result.detail["syndication"] == penalties.SYNDICATION_DEMOTE_MULTIPLIER
    # no shortener list -> untouched
    result = penalties.apply(_ctx(text="Sicily, Italy http://dlvr.it/TVMgSf", syndication_domains=frozenset()))
    assert result.detail["syndication"] == 1.0
    # a plain link -> untouched
    result = penalties.apply(_ctx(text="great read https://example.com/x", syndication_domains=SHORTENERS))
    assert result.detail["syndication"] == 1.0


def test_apply_syndication_tolerates_a_malformed_url_in_post_text():
    # urlsplit() raises ValueError ("Invalid IPv6 URL") on a bad bracketed
    # netloc; post text is untrusted, so this must not propagate -- the
    # scoring path has no try/except and would crash-loop the process.
    result = penalties.apply(
        _ctx(text="check this http://[::1 out", syndication_domains=SHORTENERS)
    )
    assert result.detail["syndication"] == 1.0
    assert result.multiplier == 1.0


def test_apply_multiplier_equals_product_of_numeric_detail():
    result = penalties.apply(
        _ctx(
            source="mastodon",
            author_id="flipboard.com/mag",
            aggregator_instances=FLIPBOARD,
            syndication_domains=SHORTENERS,
            text="headline restated http://dlvr.it/x " + NOWPLAYING,
            context_action=ContextClassification(action="devalue", devalue_multiplier=0.4),
        )
    )
    product = 1.0
    for name in _PENALTY_NAMES:
        product *= result.detail[name]
    assert abs(result.multiplier - product) < 1e-9
