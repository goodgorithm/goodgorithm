"""Platform-differentiated handling for a post whose meaning depends on
unstated context -- a Bluesky reply or quote-post, or Mastodon's
quote-inline convention (and its RE:-text/bridged-quote equivalents).

A context-dependent post is never ranked until its target is resolved --
see quote_resolver.py/mastodon_resolver.py's resolve_context() and
pipeline.resolve_context(). Deliberately pessimistic: it doesn't rank on
its own merit alone, since we don't yet know whether its referenced
content is itself excluded.

Bluesky's quote-inline/RE:-text equivalents (quote-inline, RE: <bsky.app
URL>) both reference a *Bluesky* post from a Mastodon one -- their target
resolves via quote_resolver.py's Bluesky AppView, not a Mastodon lookup.
Only a genuine in_reply_to_id needs mastodon_resolver.py. The resolver to
use is determined by the shape of context_target itself (an AT-URI vs an
{instance}/{status_id} pair), not by source -- see pipeline.resolve_context().

One registry keyed by source platform, not per-platform conditionals
scattered through pipeline.py/ranking.py -- adding a new platform later
means adding one entry here, nothing else changes.
"""

import re
from dataclasses import dataclass
from typing import Callable, Literal

from pipeline_stages import mastodon_resolver, quote_resolver

Action = Literal["exclude", "pending", "none"]
ContextKind = Literal["quote", "reply"]

# Catches both a Bridgy-Fed-bridged quote-post (which carries a
# quote-inline class, checked separately below) and a person manually
# typing "RE: <bsky.app post URL>" themselves with no such wrapper --
# matched directly since the actual signal is "this post's meaning
# depends on an unstated quoted post," not "Bridgy Fed generated this."
# Handle-based and DID-based profile URLs both match and both capture.
_BLUESKY_QUOTE_REFERENCE_RE = re.compile(r"\bre:\s*(https://bsky\.app/profile/\S+/post/\S+)", re.IGNORECASE)

# Bridgy Fed's bridged-quote marker: an anchor tagged quote-inline whose
# href is the quoted Bluesky post's web URL.
_QUOTE_INLINE_HREF_RE = re.compile(r'<a\s+class="quote-inline"\s+href="([^"]+)"', re.IGNORECASE)

_BSKY_POST_URL_RE = re.compile(r"^https://bsky\.app/profile/([^/\s]+)/post/([^/?#\s]+)")


def _bsky_url_to_at_uri(url: str) -> str | None:
    """Converts a bsky.app web URL to the AT-URI Bluesky's AppView
    actually takes. The profile segment can be a DID or a handle --
    getPosts accepts either as a valid at-identifier authority."""
    match = _BSKY_POST_URL_RE.match(url)
    if not match:
        return None
    identifier, rkey = match.groups()
    return f"at://{identifier}/app.bsky.feed.post/{rkey}"


def _bluesky_action(author_id: str, raw_json: dict, text: str) -> tuple[Action, ContextKind | None, str | None]:
    target = quote_resolver.extract_context_target(raw_json)
    if target is None:
        return "none", None, None
    kind, uri = target
    return "pending", kind, uri


def _mastodon_action(author_id: str, raw_json: dict, text: str) -> tuple[Action, ContextKind | None, str | None]:
    reply_target = mastodon_resolver.extract_reply_target(raw_json, author_id)
    if reply_target is not None:
        return "pending", "reply", reply_target

    content = (raw_json or {}).get("content")
    if isinstance(content, str) and "quote-inline" in content:
        href_match = _QUOTE_INLINE_HREF_RE.search(content)
        at_uri = _bsky_url_to_at_uri(href_match.group(1)) if href_match else None
        # Marker present but the href didn't parse into a usable AT-URI --
        # stay on the safe side (exclude) rather than silently letting an
        # unresolvable context-dependent post through as ordinary.
        return ("pending", "quote", at_uri) if at_uri else ("exclude", None, None)

    re_match = _BLUESKY_QUOTE_REFERENCE_RE.search(text or "")
    if re_match:
        at_uri = _bsky_url_to_at_uri(re_match.group(1))
        return ("pending", "quote", at_uri) if at_uri else ("exclude", None, None)

    return "none", None, None


@dataclass(frozen=True)
class PlatformPolicy:
    handler: Callable[[str, dict, str], tuple[Action, ContextKind | None, str | None]]


PLATFORM_POLICIES: dict[str, PlatformPolicy] = {
    "bluesky": PlatformPolicy(handler=_bluesky_action),
    "mastodon": PlatformPolicy(handler=_mastodon_action),
}


@dataclass(frozen=True)
class ContextClassification:
    action: Action
    context_kind: ContextKind | None = None
    context_target: str | None = None  # the target to resolve, when action == "pending"


def classify(source: str, author_id: str, raw_json: dict, text: str) -> ContextClassification:
    """What to do with a post whose full meaning may depend on missing
    context, per its source platform's policy. A platform with no entry
    here, or a post that isn't context-dependent under its platform's
    rule, is unaffected ("none")."""
    policy = PLATFORM_POLICIES.get(source)
    if policy is None:
        return ContextClassification(action="none")

    action, kind, target = policy.handler(author_id, raw_json, text)
    return ContextClassification(action=action, context_kind=kind, context_target=target)
