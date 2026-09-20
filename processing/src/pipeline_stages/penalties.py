"""A registry of content-derived, observational-only devalue signals:
`context` and `aggregator`. The labelled evaluation set behind the rest of
the scoring pipeline's validation carries no `author_id`/raw platform JSON
to compute either signal from, so neither has measured evidence either
way -- both stay active pending real data rather than being assumed safe
or unsafe.

`ranking.py`'s `compute_base_score` is `quality_score x recency_decay` and
does not read this registry's output -- `apply()`'s combined multiplier
and per-penalty detail are persisted to `processed_posts.penalty_multiplier`/
`penalty_detail` purely for audit, the same observational role
`political_score` holds.

Adding a penalty means one `PENALTIES` entry plus its evaluator -- nothing
elsewhere needs to change, since only `penalty_detail`'s persistence reads
this registry. See the wiki's Penalties page.
"""

from dataclasses import dataclass
from typing import Callable

from pipeline_stages import aggregator_demote
from pipeline_stages.context_dependency import ContextClassification


@dataclass(frozen=True)
class PenaltyContext:
    """Everything the evaluators might read, assembled once per post in
    `run_cycle`. `context_action` is the filter loop's already-computed
    `context_dependency.classify` result (re-running it here would double the
    work and the exclude has already happened)."""

    source: str
    author_id: str
    context_action: ContextClassification
    aggregator_instances: frozenset[str]


def _context(ctx: PenaltyContext) -> tuple[float, dict]:
    return ctx.context_action.devalue_multiplier, {}


def _aggregator(ctx: PenaltyContext) -> tuple[float, dict]:
    return (
        aggregator_demote.classify(ctx.source, ctx.author_id, ctx.aggregator_instances).devalue_multiplier,
        {},
    )


@dataclass(frozen=True)
class Penalty:
    name: str
    # -> (multiplier in (0.0, 1.0], extra detail merged into penalty_detail)
    evaluate: Callable[[PenaltyContext], tuple[float, dict]]


PENALTIES: tuple[Penalty, ...] = (
    Penalty("context", _context),
    Penalty("aggregator", _aggregator),
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
