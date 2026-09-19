"""The base_score devalue box: one registry that runs every content-derived
penalty and returns their combined multiplier.

`compute_base_score` is `positivity x topicality x recency_decay x
penalty_multiplier`, where `penalty_multiplier` is the product of every
registered penalty's own multiplier (`1.0` == no penalty). Most penalties
are a thin adapter around an existing stage module -- `context_dependency.py`
(devalue half only; its exclude half stays in `pipeline.py`'s filter loop),
`link_share.py`, `aggregator_demote.py`, `post_shape.py`. `quote` has no
module of its own -- it reads the already-resolved `quote_resolver.py`
`quote_content` blob. This module *composes* them; it does not absorb them.

Adding a penalty means one `PENALTIES` entry plus its evaluator -- nothing
in `ranking.py` / `pipeline.py` / `db.py` changes, since they only ever see
the single `penalty_multiplier`. The per-penalty breakdown is persisted
verbatim as `processed_posts.penalty_detail` (JSONB) for auditing. See the
wiki's Penalties page.
"""

import os
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

from pipeline_stages import aggregator_demote, hashtag_bag, link_share, post_shape
from pipeline_stages.content_filter import matches_domain_list
from pipeline_stages.context_dependency import ContextClassification
from util import url_extract

# base_score multiplier for a post whose link routes through a dedicated
# RSS->social auto-poster / share-shortener (dlvr.it, ift.tt, ...). Same
# default as aggregator_demote's -- syndicated headline, no original take.
# The domain list is db.fetch_syndication_domains()'s whole-table read,
# threaded in per post. See the wiki's Penalties page.
SYNDICATION_DEMOTE_MULTIPLIER = float(os.environ.get("SYNDICATION_DEMOTE_MULTIPLIER", "0.3"))
if not 0.0 < SYNDICATION_DEMOTE_MULTIPLIER <= 1.0:
    raise ValueError(
        f"SYNDICATION_DEMOTE_MULTIPLIER ({SYNDICATION_DEMOTE_MULTIPLIER}) must be in (0.0, 1.0]"
    )

# base_score multiplier for a post whose Bluesky quote resolved to a
# moderation-filtered quoted post (quote_resolver.py records
# quote_content = {"status": "unavailable", "reason": "filtered"} -- adult
# self-label / labeler adult label / excluded hashtag / suppressed-domain
# link on the quoted post). The outer post is scored on its own text alone,
# so a caption over adult content otherwise ranks on the caption. Devalue,
# not exclude, and a touch gentler than the 0.3 family: many matches are
# art-community endorsements of an 18+-flagged account or post whose own
# content is tame. `not_found` quotes (deleted / detached / blocked) are
# left untouched. See the wiki's Penalties page.
QUOTE_FILTERED_DEMOTE_MULTIPLIER = float(os.environ.get("QUOTE_FILTERED_DEMOTE_MULTIPLIER", "0.4"))
if not 0.0 < QUOTE_FILTERED_DEMOTE_MULTIPLIER <= 1.0:
    raise ValueError(
        f"QUOTE_FILTERED_DEMOTE_MULTIPLIER ({QUOTE_FILTERED_DEMOTE_MULTIPLIER}) must be in (0.0, 1.0]"
    )

# base_score multiplier for a post the trained political classifier scores
# above threshold but the AND-gate hard-exclude in political_exclude.py
# didn't already remove (that needs the independent centroid signal to also
# agree; this needs only the classifier). The classifier's own natural
# decision boundary (0.5, not a tuned budget) -- devalue is low-stakes
# (the post stays visible, just ranked lower), so it uses the higher-recall
# side of the tradeoff rather than the exclude gate's stricter pairing.
POLITICAL_DEVALUE_THRESHOLD = float(os.environ.get("POLITICAL_DEVALUE_THRESHOLD", "0.5"))
POLITICAL_DEMOTE_MULTIPLIER = float(os.environ.get("POLITICAL_DEMOTE_MULTIPLIER", "0.5"))
if not 0.0 < POLITICAL_DEMOTE_MULTIPLIER <= 1.0:
    raise ValueError(f"POLITICAL_DEMOTE_MULTIPLIER ({POLITICAL_DEMOTE_MULTIPLIER}) must be in (0.0, 1.0]")


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
    syndication_domains: frozenset[str]
    shape_config: dict[str, post_shape.ShapeConfig]
    quote_content: dict | None
    political_score: float | None


def _context(ctx: PenaltyContext) -> tuple[float, dict]:
    return ctx.context_action.devalue_multiplier, {}


def _link_share(ctx: PenaltyContext) -> tuple[float, dict]:
    return link_share.classify(ctx.source, ctx.raw_json, ctx.text).devalue_multiplier, {}


def _hashtag_bag(ctx: PenaltyContext) -> tuple[float, dict]:
    return hashtag_bag.classify(ctx.text).devalue_multiplier, {}


def _aggregator(ctx: PenaltyContext) -> tuple[float, dict]:
    return (
        aggregator_demote.classify(ctx.source, ctx.author_id, ctx.aggregator_instances).devalue_multiplier,
        {},
    )


def _syndication(ctx: PenaltyContext) -> tuple[float, dict]:
    # Checks every URL the post carries (extract_all_urls: structured
    # embed/card plus every URL in the text), not just the platform-
    # preferred one -- a link-preview embed and the caption text can point
    # to two different domains. A malformed URL among several is skipped,
    # not treated as a reason to stop checking the rest -- mirrors
    # content_filter.has_excluded_domain's same per-URL guard.
    for url in url_extract.extract_all_urls(ctx.source, ctx.raw_json, ctx.text):
        try:
            host = urlsplit(url).netloc.lower()
        except ValueError:
            continue
        if host and matches_domain_list(host, ctx.syndication_domains):
            return SYNDICATION_DEMOTE_MULTIPLIER, {}
    return 1.0, {}


def _quote(ctx: PenaltyContext) -> tuple[float, dict]:
    qc = ctx.quote_content
    if qc and qc.get("status") == "unavailable" and qc.get("reason") == "filtered":
        return QUOTE_FILTERED_DEMOTE_MULTIPLIER, {}
    return 1.0, {}


def _shape(ctx: PenaltyContext) -> tuple[float, dict]:
    match = post_shape.classify(ctx.text, ctx.shape_config)
    if match is None:
        return 1.0, {"shape_name": None}
    return match.devalue_multiplier, {"shape_name": match.name}


def _political(ctx: PenaltyContext) -> tuple[float, dict]:
    if ctx.political_score is None or ctx.political_score < POLITICAL_DEVALUE_THRESHOLD:
        return 1.0, {}
    return POLITICAL_DEMOTE_MULTIPLIER, {}


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
    Penalty("hashtag_bag", _hashtag_bag),
    Penalty("aggregator", _aggregator),
    Penalty("syndication", _syndication),
    Penalty("quote", _quote),
    Penalty("shape", _shape),
    Penalty("political", _political),
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
