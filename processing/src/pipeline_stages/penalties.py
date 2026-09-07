"""The base_score devalue box: one registry that runs every content-derived
penalty and returns their combined multiplier.

`compute_base_score` is `positivity x topicality x recency_decay x
penalty_multiplier`, where `penalty_multiplier` is the product of every
registered penalty's own multiplier (`1.0` == no penalty). Each penalty is
a thin adapter around an existing stage module -- `context_dependency.py`
(devalue half only; its exclude half stays in `pipeline.py`'s filter loop),
`link_share.py`, `aggregator_demote.py`, `post_shape.py`. This module
*composes* them; it does not absorb them.

Adding a penalty means one `PENALTIES` entry plus its evaluator -- nothing
in `ranking.py` / `pipeline.py` / `db.py` changes, since they only ever see
the single `penalty_multiplier`. The per-penalty breakdown is persisted
verbatim as `processed_posts.penalty_detail` (JSONB) for auditing. See the
wiki's Penalties page.
"""

from dataclasses import dataclass
from typing import Callable

from pipeline_stages import aggregator_demote, link_share, post_shape
from pipeline_stages.context_dependency import ContextClassification


@dataclass(frozen=True)
class PenaltyContext:
    """Everything the evaluators might read, assembled once per post in
    `run_cycle`. `context_action` is the filter loop's already-computed
    `context_dependency.classify` result (re-running it here would double the
    work and the exclude has already happened)."""

    source: str
    author_id: str
    raw_json: dict
    text: str
    context_action: ContextClassification
    aggregator_instances: frozenset[str]
    shape_config: dict[str, post_shape.ShapeConfig]


def _context(ctx: PenaltyContext) -> tuple[float, dict]:
    return ctx.context_action.devalue_multiplier, {}


def _link_share(ctx: PenaltyContext) -> tuple[float, dict]:
    return link_share.classify(ctx.source, ctx.raw_json, ctx.text).devalue_multiplier, {}


def _aggregator(ctx: PenaltyContext) -> tuple[float, dict]:
    return (
        aggregator_demote.classify(ctx.source, ctx.author_id, ctx.aggregator_instances).devalue_multiplier,
        {},
    )


def _shape(ctx: PenaltyContext) -> tuple[float, dict]:
    match = post_shape.classify(ctx.text, ctx.shape_config)
    if match is None:
        return 1.0, {"shape_name": None}
    return match.devalue_multiplier, {"shape_name": match.name}


@dataclass(frozen=True)
class Penalty:
    name: str
    # -> (multiplier in (0.0, 1.0], extra detail merged into penalty_detail)
    evaluate: Callable[[PenaltyContext], tuple[float, dict]]


# Order is cosmetic (the product is commutative) but kept
# ingestion-adjacent -> feed-adjacent for readability.
PENALTIES: tuple[Penalty, ...] = (
    Penalty("context", _context),
    Penalty("link_share", _link_share),
    Penalty("aggregator", _aggregator),
    Penalty("shape", _shape),
)


@dataclass(frozen=True)
class PenaltyResult:
    multiplier: float  # product of every penalty's multiplier; base_score reads this
    detail: dict  # {penalty_name: multiplier, ...} + merged extras; persisted as penalty_detail JSONB


def apply(ctx: PenaltyContext) -> PenaltyResult:
    product = 1.0
    detail: dict = {}
    for penalty in PENALTIES:
        multiplier, extra = penalty.evaluate(ctx)
        product *= multiplier
        detail[penalty.name] = multiplier
        detail.update(extra)
    return PenaltyResult(multiplier=product, detail=detail)
