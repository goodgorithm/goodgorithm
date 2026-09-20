"""Platform-differentiated handling for a post whose meaning depends on
unstated context -- a Bluesky reply or quote-post, or Mastodon's
quote-inline convention (and its RE:-text/bridged-quote equivalents).

Bluesky: a context-dependent post is never ranked until its target is
resolved -- see quote_resolver.py's resolve_context() and
pipeline.resolve_context(). Deliberately pessimistic: it doesn't rank on
its own merit alone, since we don't yet know whether its referenced
content is itself excluded (see issue #292). Mastodon's equivalent cases
still hard-exclude for now (issue #293 generalizes this the same way).

One registry keyed by source platform, not per-platform conditionals
scattered through pipeline.py/ranking.py -- adding a new platform later
means adding one entry here, nothing else changes.
"""

import re
from dataclasses import dataclass
from typing import Callable, Literal

from pipeline_stages import quote_resolver

Action = Literal["exclude", "pending", "none"]
ContextKind = Literal["quote", "reply"]

# Catches both a Bridgy-Fed-bridged quote-post (which carries a
# quote-inline class, checked separately) and a person manually typing
# "RE: <bsky.app post URL>" themselves with no such wrapper -- matched
# directly since the actual signal is "this post's meaning depends on an
# unstated quoted post," not "Bridgy Fed generated this." Handle-based and
# DID-based profile URLs both match.
_BLUESKY_QUOTE_REFERENCE_RE = re.compile(r"\bre:\s*https://bsky\.app/profile/\S+/post/\S+", re.IGNORECASE)


def _bluesky_action(raw_json: dict, text: str) -> tuple[Action, ContextKind | None, str | None]:
    target = quote_resolver.extract_context_target(raw_json)
    if target is None:
        return "none", None, None
    kind, uri = target
    return "pending", kind, uri


def _mastodon_action(raw_json: dict, text: str) -> tuple[Action, ContextKind | None, str | None]:
    if (raw_json or {}).get("in_reply_to_id") is not None:
        return "exclude", None, None
    content = (raw_json or {}).get("content")
    if isinstance(content, str) and "quote-inline" in content:
        return "exclude", None, None
    if _BLUESKY_QUOTE_REFERENCE_RE.search(text or ""):
        return "exclude", None, None
    return "none", None, None


@dataclass(frozen=True)
class PlatformPolicy:
    handler: Callable[[dict, str], tuple[Action, ContextKind | None, str | None]]


PLATFORM_POLICIES: dict[str, PlatformPolicy] = {
    "bluesky": PlatformPolicy(handler=_bluesky_action),
    "mastodon": PlatformPolicy(handler=_mastodon_action),
}


@dataclass(frozen=True)
class ContextClassification:
    action: Action
    context_kind: ContextKind | None = None
    context_target: str | None = None  # the URI to resolve, when action == "pending"


def classify(source: str, raw_json: dict, text: str) -> ContextClassification:
    """What to do with a post whose full meaning may depend on missing
    context, per its source platform's policy. A platform with no entry
    here, or a post that isn't context-dependent under its platform's
    rule, is unaffected ("none")."""
    policy = PLATFORM_POLICIES.get(source)
    if policy is None:
        return ContextClassification(action="none")

    action, kind, target = policy.handler(raw_json, text)
    return ContextClassification(action=action, context_kind=kind, context_target=target)
