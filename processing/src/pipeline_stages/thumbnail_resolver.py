import html
import ipaddress
import logging
import os
import re
import socket
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger("processing")

# Fills in a link-card thumbnail when the source platform didn't capture
# one (a poster's Bluesky client with no OG-fetch of its own, or a
# Mastodon server whose own card-fetch failed) -- the same og:image
# mechanism Mastodon's server already uses for the cards that do work.
#
# Unlike util/bluesky_appview.py's Bluesky AppView calls (a fixed, trusted
# host), this fetches arbitrary URLs a random poster put in their post --
# a real SSRF surface. _is_safe_public_url is the required gate, not an
# optional extra: without it a malicious post could point at a cloud
# metadata endpoint or an internal service and have this dutifully fetch
# it. See the wiki's Thumbnail Resolution page.
THUMBNAIL_RESOLVER_REQUEST_TIMEOUT_SECONDS = int(
    os.environ.get("THUMBNAIL_RESOLVER_REQUEST_TIMEOUT_SECONDS", "10")
)
THUMBNAIL_RESOLVER_MAX_REDIRECTS = int(os.environ.get("THUMBNAIL_RESOLVER_MAX_REDIRECTS", "3"))
# og/twitter tags are always in <head>, no legitimate page needs more.
THUMBNAIL_RESOLVER_MAX_RESPONSE_BYTES = int(
    os.environ.get("THUMBNAIL_RESOLVER_MAX_RESPONSE_BYTES", str(2 * 1024 * 1024))
)
# A project identity string sent to third-party servers, not an operator
# tunable -- not an env var, same reasoning as util/bluesky_appview.py's
# APPVIEW_BASE.
USER_AGENT = "Goodgorithm/0.1 (+https://github.com/goodgorithm/goodgorithm)"

# og:image and twitter:image are matched by two separate regex pairs, not
# one combined pattern -- a combined pattern just finds whichever tag
# happens to appear first in the document, which isn't the same as
# preferring og:image (the more universally-supported tag) whenever both
# are present. Each pair handles both attribute orderings Mastodon/other
# generators use (property/content vs content/property).
def _meta_content_patterns(tag: str) -> tuple[re.Pattern, re.Pattern]:
    forward = re.compile(
        rf'<meta\s+[^>]*(?:property|name)\s*=\s*["\']{tag}["\'][^>]*content\s*=\s*["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    reverse = re.compile(
        rf'<meta\s+[^>]*content\s*=\s*["\']([^"\']+)["\'][^>]*(?:property|name)\s*=\s*["\']{tag}["\']',
        re.IGNORECASE,
    )
    return forward, reverse


_OG_IMAGE_RE, _OG_IMAGE_RE_REV = _meta_content_patterns("og:image")
_TWITTER_IMAGE_RE, _TWITTER_IMAGE_RE_REV = _meta_content_patterns("twitter:image")


def _is_safe_public_url(url: str) -> bool:
    """Rejects anything that could point at internal/private infrastructure
    before we ever connect. Resolves the hostname now (not just validating
    the string) and checks every resolved address -- a malicious post could
    otherwise name an internal/reserved address directly. Called again on
    every redirect hop in resolve_thumbnail, since a URL can pass this
    check and then redirect somewhere unsafe."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        addr_info = socket.getaddrinfo(parsed.hostname, None)
        for family_info in addr_info:
            ip = ipaddress.ip_address(family_info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except (ValueError, socket.gaierror, UnicodeError):
        return False


def _fetch_html(url: str, depth: int = 0) -> str | None:
    """Manually follows redirects (bounded) rather than requests' own
    allow_redirects=True, so each hop can be re-validated with
    _is_safe_public_url before following it -- a URL could pass the
    initial check and still redirect to an internal address."""
    if depth > THUMBNAIL_RESOLVER_MAX_REDIRECTS or not _is_safe_public_url(url):
        return None

    try:
        response = requests.get(
            url,
            timeout=THUMBNAIL_RESOLVER_REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
            stream=True,
            allow_redirects=False,
        )
    except requests.RequestException as err:
        logger.warning("thumbnail fetch failed for %s: %s", url, err)
        return None

    with response:
        if response.is_redirect:
            location = response.headers.get("Location")
            if not location:
                return None
            return _fetch_html(urljoin(url, location), depth + 1)

        if response.status_code != 200:
            return None

        try:
            raw = response.raw.read(THUMBNAIL_RESOLVER_MAX_RESPONSE_BYTES, decode_content=True)
            return raw.decode(response.encoding or "utf-8", errors="ignore")
        except (requests.RequestException, UnicodeError) as err:
            logger.warning("thumbnail fetch failed reading body for %s: %s", url, err)
            return None


def resolve_thumbnail(url: str) -> str | None:
    """Fetches the linked page and extracts its og:image (falling back to
    twitter:image). Never raises -- any failure (unsafe URL, network error,
    timeout, no matching tag) just means no generated thumbnail for this
    post, same "never blocks or crashes a cycle, no retry" discipline as
    quote_resolver.py, since each raw_post is only ever scored once."""
    page_html = _fetch_html(url)
    if page_html is None:
        return None

    match = (
        _OG_IMAGE_RE.search(page_html)
        or _OG_IMAGE_RE_REV.search(page_html)
        or _TWITTER_IMAGE_RE.search(page_html)
        or _TWITTER_IMAGE_RE_REV.search(page_html)
    )
    if not match:
        return None

    # og:image content attributes are HTML-encoded like any other
    # attribute value -- must be unescaped, or an "&amp;" in the query
    # string would corrupt the URL.
    image_url = html.unescape(match.group(1))
    return image_url if _is_safe_public_url(image_url) else None


def resolve_thumbnails(urls: list[str]) -> dict[str, str | None]:
    """One fetch per distinct URL -- no batching API exists for arbitrary
    third-party pages (unlike quote_resolver.py's Bluesky AppView), but
    multiple posts linking to the same page (a widely-shared article)
    should only trigger one fetch, not one per post."""
    return {url: resolve_thumbnail(url) for url in dict.fromkeys(urls)}


_TEXT_URL_RE = re.compile(r"https?://\S+")


def extract_link_needing_thumbnail(source: str, raw_json: dict, text: str) -> str | None:
    """The link URL that should get a generated thumbnail, or None if this
    post has no external-link embed or already has a source-provided
    thumbnail. Hand-mirrors api/src/attachments.ts's parseBlueskyExternal/
    parseMastodonCard thumbnail-presence checks -- the same Python<->
    TypeScript hand-sync CLAUDE.md documents for Attachment/QuoteContent,
    no shared package across that boundary in this repo."""
    if source == "bluesky":
        record = (raw_json or {}).get("commit", {}).get("record", {})
        embed = record.get("embed") if isinstance(record, dict) else None
        if not isinstance(embed, dict) or embed.get("$type") != "app.bsky.embed.external":
            return None
        external = embed.get("external")
        if not isinstance(external, dict) or external.get("thumb"):
            return None
        uri = external.get("uri")
        return uri if isinstance(uri, str) else None

    if source == "mastodon":
        card = (raw_json or {}).get("card")
        if isinstance(card, dict):
            if card.get("image"):
                return None  # already has a source thumbnail
            url = card.get("url")
            if isinstance(url, str):
                return url

        # No usable card.url is common, not an edge case: Mastodon's own
        # card generation is async per-instance, and isn't always done by
        # the time we poll a post -- the *identical* post relayed through
        # a different instance can have a full card while this one has
        # card: null entirely. Falls back to the first URL in the post's
        # own text, which already has any truncated-link href resolved
        # into it at ingestion time, rather than giving up.
        match = _TEXT_URL_RE.search(text)
        return match.group(0) if match else None

    return None
