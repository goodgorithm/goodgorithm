"""A registry of content-derived, observational-only devalue signals:
currently just `aggregator`. The labelled evaluation set behind the rest of
the scoring pipeline's validation carries no `author_id`/raw platform JSON
to compute it from, so it has no measured evidence either way -- it stays
active pending real data rather than being assumed safe or unsafe.

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


@dataclass(frozen=True)
class PenaltyContext:
    """Everything the evaluators might read, assembled once per post in
    `run_cycle`."""

    source: str
    author_id: str
    aggregator_instances: frozenset[str]


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


PENALTIES: tuple[Penalty, ...] = (Penalty("aggregator", _aggregator),)


@dataclass(frozen=True)
class PenaltyResult:
    multiplier: float  # product of every penalty's multiplier; audit-only, never applied to base_score
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
