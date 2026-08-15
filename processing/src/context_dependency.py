"""Platform-differentiated handling for posts whose meaning depends on
unstated context -- a reply, or Mastodon's `quote-inline` convention
(issue #33). Resolving that context the way quote_resolver.py resolves
Bluesky quote-posts doesn't scale here: replies run 66,000+/day across
both platforms combined, vs. quote-resolution's much smaller footprint,
and Mastodon replies would mean trusting arbitrary, unvetted instances.
So each platform gets its own policy instead -- exclude outright, or
keep the post but down-weight it in ranking.

One registry keyed by source platform, not per-platform conditionals
scattered through pipeline.py/ranking.py -- adding a new platform later
means adding one entry here, nothing else changes.

#33 investigation (2026-08-14) found the two platforms aren't remotely
the same problem: Bluesky replies are 51.6% of Bluesky's currently-
eligible pool with an eligibility rate almost identical to non-replies
(volume too large, quality too close to justify a hard cut). Mastodon's
structured replies and quote-inline are each only ~4-6% of its eligible
pool, and structured replies specifically skew notably less positive --
cheap to exclude outright without denting Mastodon's contribution.
"""

from dataclasses import dataclass
from typing import Callable, Literal

Action = Literal["exclude", "devalue", "none"]


def _bluesky_action(author_id: str, raw_json: dict) -> Action:
    record = (raw_json or {}).get("commit", {}).get("record", {})
    reply = record.get("reply") if isinstance(record, dict) else None
    if not isinstance(reply, dict):
        return "none"

    # Self-reply-thread continuations (same author replying to their own
    # prior post) read far more like a coherent, intended-to-stand-
    # together post than a reply to someone else -- the reply-parent's
    # author is embedded directly in its AT-URI
    # (at://<did>/<collection>/<rkey>), so this is a free structural
    # check, no resolution call needed (mirrors quote_resolver.py's own
    # defensive AT-URI handling). Only replies to a *different* author
    # count as context-dependent.
    parent = reply.get("parent")
    parent_uri = parent.get("uri") if isinstance(parent, dict) else None
    if isinstance(parent_uri, str):
        parts = parent_uri.split("/")
        if len(parts) > 2 and parts[2] == author_id:
            return "none"

    return "devalue"


def _mastodon_action(author_id: str, raw_json: dict) -> Action:
    if (raw_json or {}).get("in_reply_to_id") is not None:
        return "exclude"
    content = (raw_json or {}).get("content")
    if isinstance(content, str) and "quote-inline" in content:
        return "exclude"
    return "none"


@dataclass(frozen=True)
class PlatformPolicy:
    handler: Callable[[str, dict], Action]
    # Only consulted when handler() returns "devalue" -- exclude-only
    # platforms never read this.
    devalue_multiplier: float = 1.0


PLATFORM_POLICIES: dict[str, PlatformPolicy] = {
    "bluesky": PlatformPolicy(handler=_bluesky_action, devalue_multiplier=0.4),
    "mastodon": PlatformPolicy(handler=_mastodon_action),
}


@dataclass(frozen=True)
class ContextClassification:
    action: Action
    devalue_multiplier: float = 1.0  # base_score multiplier; 1.0 == no penalty


def classify(source: str, author_id: str, raw_json: dict) -> ContextClassification:
    """What to do with a post whose full meaning may depend on missing
    context, per its source platform's policy. A platform with no entry
    here, or a post that isn't context-dependent under its platform's
    rule, is unaffected ("none")."""
    policy = PLATFORM_POLICIES.get(source)
    if policy is None:
        return ContextClassification(action="none")

    action = policy.handler(author_id, raw_json)
    if action == "devalue":
        return ContextClassification(action="devalue", devalue_multiplier=policy.devalue_multiplier)
    return ContextClassification(action=action)
