"""Down-weights a post whose Mastodon home instance is a known content
aggregator -- Flipboard's federating "magazine" accounts and similar
services that syndicate curated headline/link reposts into the fediverse
rather than posting original content. Enthusiastic headline text scores
well on sentiment and clears the topicality floor, so without this one
automated aggregator can dominate a large share of the ranked feed
(flipboard.com alone was ~34% of ranked Mastodon content). Not off-mission
enough to hard-exclude the way content_filter/context_dependency do -- some
reshares are genuinely worth seeing -- so this is a base_score devalue
multiplier, the same category as context_dependency.py / link_share.py.

The instance list is db.fetch_aggregator_instances()'s whole-table read
(the aggregator_instances table), moderator-curated and refreshed via
db.fetch_moderation_lists()'s cache -- deliberately a separate table from
suppressed_domains, since adding a domain there hard-excludes and this only
devalues.

Mastodon-only: Bluesky has no per-instance federation concept, so there's
no home instance to check and a Bluesky post is always unaffected.
"""

import os
from dataclasses import dataclass

from pipeline_stages import bot_filter
from pipeline_stages.content_filter import matches_domain_list

# base_score multiplier for a post from a listed aggregator instance --
# harder than context_dependency.py's / link_share.py's 0.4 default,
# reflecting that these carry no original commentary at all. See the wiki's
# Ranking page. Treat any non-default value as unvalidated against real
# production data.
AGGREGATOR_DEMOTE_MULTIPLIER = float(os.environ.get("AGGREGATOR_DEMOTE_MULTIPLIER", "0.3"))
if not 0.0 < AGGREGATOR_DEMOTE_MULTIPLIER <= 1.0:
    raise ValueError(
        f"AGGREGATOR_DEMOTE_MULTIPLIER ({AGGREGATOR_DEMOTE_MULTIPLIER}) must be in (0.0, 1.0]"
    )


@dataclass(frozen=True)
class AggregatorClassification:
    is_aggregator: bool
    devalue_multiplier: float = 1.0  # base_score multiplier; 1.0 == no penalty


def classify(
    source: str, author_id: str, aggregator_instances: frozenset[str]
) -> AggregatorClassification:
    """Whether a post's Mastodon home instance is a listed aggregator and,
    if so, the base_score multiplier to apply. A Bluesky post, a Mastodon
    post from an unlisted instance, or an empty list is unaffected."""
    if source != "mastodon" or not aggregator_instances:
        return AggregatorClassification(is_aggregator=False)

    # canonical_account_id yields `user@host`, reconstructing
    # `user@{polled_instance}` when the polled instance is the account's own
    # home instance (so a bare local `acct` still resolves to a real host).
    home_instance = bot_filter.canonical_account_id(source, author_id).rpartition("@")[2].lower()
    if home_instance and matches_domain_list(home_instance, aggregator_instances):
        return AggregatorClassification(
            is_aggregator=True, devalue_multiplier=AGGREGATOR_DEMOTE_MULTIPLIER
        )
    return AggregatorClassification(is_aggregator=False)
