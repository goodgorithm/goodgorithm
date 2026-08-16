"""Platform-differentiated handling for posts whose meaning depends on
unstated context -- a reply, or Mastodon's `quote-inline` convention.
Resolving that context the way quote_resolver.py resolves Bluesky
quote-posts doesn't scale here -- replies run orders of magnitude higher
volume than quote-resolution's footprint, and Mastodon replies would mean
trusting arbitrary, unvetted instances. So each platform gets its own
policy instead -- exclude outright, or keep the post but down-weight it
in ranking. See the wiki's Pipeline Internals page for the full
per-platform reasoning and the volume/eligibility numbers behind it.

One registry keyed by source platform, not per-platform conditionals
scattered through pipeline.py/ranking.py -- adding a new platform later
means adding one entry here, nothing else changes.
"""

import os
import re
from dataclasses import dataclass
from typing import Callable, Literal

Action = Literal["exclude", "devalue", "none"]

# base_score multiplier for a Bluesky reply to a different author -- see
# the wiki's Pipeline Internals page.
CONTEXT_DEPENDENCY_BLUESKY_DEVALUE_MULTIPLIER = float(
    os.environ.get("CONTEXT_DEPENDENCY_BLUESKY_DEVALUE_MULTIPLIER", "0.4")
)

# Catches both a Bridgy-Fed-bridged quote-post (which carries a
# quote-inline class, checked separately below) and a person manually
# typing "RE: <bsky.app post URL>" themselves with no such wrapper --
# matched directly since the actual signal is "this post's meaning
# depends on an unstated quoted post," not "Bridgy Fed generated this."
# Handle-based and DID-based profile URLs both match. See the wiki's
# Pipeline Internals page.
_BLUESKY_QUOTE_REFERENCE_RE = re.compile(r"\bre:\s*https://bsky\.app/profile/\S+/post/\S+", re.IGNORECASE)


def _bluesky_action(author_id: str, raw_json: dict, text: str) -> Action:
    record = (raw_json or {}).get("commit", {}).get("record", {})
    reply = record.get("reply") if isinstance(record, dict) else None
    if not isinstance(reply, dict):
        return "none"

    # Self-reply-thread continuations read more like one coherent post
    # than a reply to someone else -- the reply-parent's author is
    # embedded directly in its AT-URI (at://<did>/<collection>/<rkey>), a
    # free structural check with no resolution call needed. Only replies
    # to a *different* author count as context-dependent. See the wiki's
    # Pipeline Internals page.
    parent = reply.get("parent")
    parent_uri = parent.get("uri") if isinstance(parent, dict) else None
    if isinstance(parent_uri, str):
        parts = parent_uri.split("/")
        if len(parts) > 2 and parts[2] == author_id:
            return "none"

    return "devalue"


def _mastodon_action(author_id: str, raw_json: dict, text: str) -> Action:
    if (raw_json or {}).get("in_reply_to_id") is not None:
        return "exclude"
    content = (raw_json or {}).get("content")
    if isinstance(content, str) and "quote-inline" in content:
        return "exclude"
    if _BLUESKY_QUOTE_REFERENCE_RE.search(text or ""):
        return "exclude"
    return "none"


@dataclass(frozen=True)
class PlatformPolicy:
    handler: Callable[[str, dict, str], Action]
    # Only consulted when handler() returns "devalue" -- exclude-only
    # platforms never read this.
    devalue_multiplier: float = 1.0


PLATFORM_POLICIES: dict[str, PlatformPolicy] = {
    "bluesky": PlatformPolicy(
        handler=_bluesky_action, devalue_multiplier=CONTEXT_DEPENDENCY_BLUESKY_DEVALUE_MULTIPLIER
    ),
    "mastodon": PlatformPolicy(handler=_mastodon_action),
}


@dataclass(frozen=True)
class ContextClassification:
    action: Action
    devalue_multiplier: float = 1.0  # base_score multiplier; 1.0 == no penalty


def classify(source: str, author_id: str, raw_json: dict, text: str) -> ContextClassification:
    """What to do with a post whose full meaning may depend on missing
    context, per its source platform's policy. A platform with no entry
    here, or a post that isn't context-dependent under its platform's
    rule, is unaffected ("none")."""
    policy = PLATFORM_POLICIES.get(source)
    if policy is None:
        return ContextClassification(action="none")

    action = policy.handler(author_id, raw_json, text)
    if action == "devalue":
        return ContextClassification(action="devalue", devalue_multiplier=policy.devalue_multiplier)
    return ContextClassification(action=action)
