import { buildBlueskyPostUrl } from "./permalink";
import type { Attachment, QuoteContent } from "./types";

export interface AttachmentSource {
  source: "bluesky" | "mastodon";
  author_id: string;
  text: string;
  bluesky_embed: unknown;
  // record.reply, raw -- only Bluesky's structured-reply field.
  bluesky_reply: unknown;
  mastodon_media: unknown;
  mastodon_card: unknown;
  mastodon_sensitive: boolean | null;
  bluesky_labels: unknown;
  // context_content is the current column; quote_content is read only as
  // a fallback for a row processing/ scored before it existed.
  context_content: unknown;
  quote_content: unknown;
  // processing/'s context_dependency.classify() already determined this
  // once (quote takes priority over reply by construction, so it's never
  // both) -- trusted directly for a Mastodon row rather than re-derived
  // from raw_json/text here, which would duplicate that module's
  // quote-inline/RE:/in_reply_to_id detection regexes across the
  // Python<->TypeScript boundary a second time. Unused on the Bluesky
  // side, which re-derives quote-vs-reply from its own embed/reply shape
  // directly (unambiguous there, no regex needed).
  context_kind: string | null;
  generated_thumbnail_url: string | null;
}

export interface AttachmentResult {
  attachments: Attachment[];
  sensitive: boolean;
}

// Bluesky's own CDN endpoints -- external protocol facts, not something
// an operator would tune, so not env vars (same treatment processing/
// gives its own Bluesky AppView URL). See the wiki's API Internals page.
const BLUESKY_CDN_BASE = "https://cdn.bsky.app/img";
const BLUESKY_VIDEO_CDN_BASE = "https://video.bsky.app/watch";

// Both resolve for real did+cid pairs from post images and link-card
// thumbnails alike (different embed fields, same blob-storage mechanism),
// no auth needed. See the wiki's API Internals page.
function blueskyImageUrls(did: string, cid: string): { thumbnailUrl: string; fullUrl: string } {
  return {
    thumbnailUrl: `${BLUESKY_CDN_BASE}/feed_thumbnail/plain/${did}/${cid}@jpeg`,
    fullUrl: `${BLUESKY_CDN_BASE}/feed_fullsize/plain/${did}/${cid}@jpeg`,
  };
}

// external.uri (Bluesky) and card.url (Mastodon) come verbatim from
// arbitrary user posts - cheaper and safer to filter non-http(s) schemes
// out here than to trust every downstream renderer never to trip on one.
function isHttpUrl(url: unknown): url is string {
  if (typeof url !== "string") return false;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function nonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

// A Bluesky client can drop a bare URL into post text with no
// app.bsky.embed.external card of its own. processing/'s
// thumbnail_resolver derives a thumbnail from a YouTube video id with no
// fetch and writes it to generated_thumbnail_url; a non-null value on a
// Bluesky row with no external embed is the signal it did. This
// synthesizes the link card api/ would otherwise never build. YOUTUBE_HOSTS
// and the first-URL / trailing-punctuation handling are hand-synced with
// thumbnail_resolver.extract_link_needing_thumbnail (no shared package
// across the Python<->TypeScript boundary, per CLAUDE.md).
const YOUTUBE_HOSTS = new Set([
  "youtube.com",
  "www.youtube.com",
  "m.youtube.com",
  "music.youtube.com",
  "youtu.be",
]);
const TEXT_URL_RE = /https?:\/\/\S+/;
const URL_TRAILING_PUNCTUATION_RE = /[).,!?;:'"]+$/;

function youtubeLinkFromText(text: string, generatedThumbnailUrl: string | null): Attachment | null {
  if (!isHttpUrl(generatedThumbnailUrl)) return null;

  const match = text.match(TEXT_URL_RE);
  if (!match) return null;
  const url = match[0].replace(URL_TRAILING_PUNCTUATION_RE, "");

  let host: string;
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return null;
  }
  if (!YOUTUBE_HOSTS.has(host)) return null;

  return {
    kind: "link",
    url,
    title: null,
    description: null,
    thumbnailUrl: generatedThumbnailUrl,
    providerName: null,
  };
}

interface BlueskyImageItem {
  alt?: unknown;
  image?: { ref?: { $link?: unknown } };
  aspectRatio?: { width?: unknown; height?: unknown };
}

function parseBlueskyImages(did: string, images: unknown): Attachment[] {
  if (!Array.isArray(images)) return [];

  const result: Attachment[] = [];
  for (const item of images) {
    if (typeof item !== "object" || item === null) continue;
    const img = item as BlueskyImageItem;
    const cid = img.image?.ref?.$link;
    if (typeof cid !== "string") continue;

    // alt is a required string in Bluesky's lexicon, but Jetstream relays
    // whatever a client actually sent with no schema validation - real
    // production data has both null and "" cases, handle both.
    const alt = typeof img.alt === "string" ? img.alt : null;
    const width = typeof img.aspectRatio?.width === "number" ? img.aspectRatio.width : null;
    const height = typeof img.aspectRatio?.height === "number" ? img.aspectRatio.height : null;

    result.push({ kind: "image", ...blueskyImageUrls(did, cid), alt, width, height });
  }
  return result;
}

interface BlueskyExternal {
  uri?: unknown;
  title?: unknown;
  description?: unknown;
  thumb?: { ref?: { $link?: unknown } };
}

function parseBlueskyExternal(did: string, external: unknown, generatedThumbnailUrl: string | null): Attachment | null {
  if (typeof external !== "object" || external === null) return null;
  const ext = external as BlueskyExternal;
  if (!isHttpUrl(ext.uri)) return null;

  const cid = ext.thumb?.ref?.$link;
  const sourceThumbnailUrl = typeof cid === "string" ? blueskyImageUrls(did, cid).thumbnailUrl : null;
  // Falls back to processing/'s own og:image fetch (thumbnail_resolver.py)
  // when the poster's own client didn't capture one - never overrides a
  // real source thumbnail when one exists. See the wiki's Thumbnail
  // Resolution page.
  const thumbnailUrl = sourceThumbnailUrl ?? (isHttpUrl(generatedThumbnailUrl) ? generatedThumbnailUrl : null);

  return {
    kind: "link",
    url: ext.uri,
    title: nonEmptyString(ext.title),
    description: nonEmptyString(ext.description),
    thumbnailUrl,
    providerName: null, // Bluesky external embeds carry no provider/site-name field
  };
}

interface BlueskyVideoEmbed {
  video?: { ref?: { $link?: unknown } };
  aspectRatio?: { width?: unknown; height?: unknown };
  presentation?: unknown;
}

// The raw record (what Jetstream relays, all we ever store) only has a
// blob ref - no ready-to-play URL. The playlist URL is deterministically
// constructable client-side from did+videoCid, same pattern as
// blueskyImageUrls above, no AppView call needed. thumbnailUrl is only
// available via the AppView's hydrated view shape, not the raw record -
// not worth a network call just for a poster frame, ships null for now.
// See the wiki's API Internals page.
function parseBlueskyVideo(did: string, embed: unknown): Attachment | null {
  if (typeof embed !== "object" || embed === null) return null;
  const typed = embed as BlueskyVideoEmbed;
  const cid = typed.video?.ref?.$link;
  if (typeof cid !== "string") return null;

  const width = typeof typed.aspectRatio?.width === "number" ? typed.aspectRatio.width : null;
  const height = typeof typed.aspectRatio?.height === "number" ? typed.aspectRatio.height : null;

  return {
    kind: "video",
    playlistUrl: `${BLUESKY_VIDEO_CDN_BASE}/${did}/${cid}/playlist.m3u8`,
    thumbnailUrl: null,
    isGif: typed.presentation === "gif",
    width,
    height,
  };
}

const AT_URI_PATTERN = /^at:\/\/([^/]+)\/([^/]+)\/([^/]+)$/;

// context_content (or, for a pre-migration row, quote_content) is a
// straight column on processed_posts, written by processing/'s
// quote_resolver.py in the exact shape below - this is a defensive
// validation pass (never trust stored JSON blindly, same rule every
// other field in this file follows), not a transform. Shared by both the
// "quote" and "reply" Attachment kinds below -- same resolved shape
// either way.
function parseContextContent(raw: unknown): QuoteContent | null {
  if (typeof raw !== "object" || raw === null) return null;
  const typed = raw as { status?: unknown; text?: unknown; author?: unknown; createdAt?: unknown; reason?: unknown };

  if (typed.status === "unavailable") {
    return typed.reason === "not_found" || typed.reason === "filtered"
      ? { status: "unavailable", reason: typed.reason }
      : null;
  }

  if (typed.status === "available" && typeof typed.text === "string" && typeof typed.author === "object" && typed.author !== null) {
    const author = typed.author as { displayName?: unknown; handle?: unknown; avatarUrl?: unknown };
    return {
      status: "available",
      author: {
        displayName: typeof author.displayName === "string" ? author.displayName : null,
        handle: typeof author.handle === "string" ? author.handle : null,
        avatarUrl: typeof author.avatarUrl === "string" ? author.avatarUrl : null,
      },
      text: typed.text,
      createdAt: typeof typed.createdAt === "string" ? typed.createdAt : null,
    };
  }

  return null;
}

// The raw context_content blob carries a url field (added by
// processing/'s quote_resolver.py/mastodon_resolver.py) that never makes
// it into the publicly-typed QuoteContent above -- QuoteContent is purely
// the display shape (author/text/createdAt), while url is this file's own
// internal signal for whether there's anything to link a Mastodon
// quote/reply attachment to yet at all. Bluesky's own quote/reply display
// never needs this -- it builds its permalink separately, straight from
// the referencing post's own raw_json, no network call required.
function extractContextUrl(raw: unknown): string | null {
  if (typeof raw !== "object" || raw === null) return null;
  const url = (raw as { url?: unknown }).url;
  return isHttpUrl(url) ? url : null;
}

// Mastodon's own equivalent of parseBlueskyQuote/parseBlueskyReply --
// diverges from them because Mastodon's raw_json never carries a
// ready-to-use target URL of its own (see extractContextUrl above), so
// there's nothing to attach until resolution has actually produced one.
// context_kind is already "quote" xor "reply" xor null by construction
// (context_dependency.classify() resolves at most one target per post),
// so no additional priority logic is needed here the way Bluesky's
// quote-before-reply check requires.
function parseMastodonContext(contextKind: string | null, raw: unknown): Attachment | null {
  if (contextKind !== "quote" && contextKind !== "reply") return null;
  const url = extractContextUrl(raw);
  if (url === null) return null; // not yet resolved (pending), or a pre-migration row
  return { kind: contextKind, url, content: parseContextContent(raw) };
}

function parseBlueskyQuote(record: unknown, quoteContent: QuoteContent | null): Attachment | null {
  if (typeof record !== "object" || record === null) return null;
  const uri = (record as { uri?: unknown }).uri;
  if (typeof uri !== "string") return null;

  // uri is a generic at://{did}/{collection}/{rkey} reference - can point
  // at a list, starter pack, or feed generator, not just a post. Only
  // build a permalink when it's actually quoting a post.
  const match = AT_URI_PATTERN.exec(uri);
  if (!match) return null;
  const [, did, collection, rkey] = match;
  if (collection !== "app.bsky.feed.post") return null;

  return { kind: "quote", url: buildBlueskyPostUrl(did, rkey), content: quoteContent };
}

// Mirrors parseBlueskyQuote's shape exactly, just reading record.reply's
// parent.uri instead of embed.record.uri -- same AT-URI form either way.
function parseBlueskyReply(reply: unknown, contextContent: QuoteContent | null): Attachment | null {
  if (typeof reply !== "object" || reply === null) return null;
  const parent = (reply as { parent?: unknown }).parent;
  if (typeof parent !== "object" || parent === null) return null;
  const uri = (parent as { uri?: unknown }).uri;
  if (typeof uri !== "string") return null;

  const match = AT_URI_PATTERN.exec(uri);
  if (!match) return null;
  const [, did, collection, rkey] = match;
  if (collection !== "app.bsky.feed.post") return null;

  return { kind: "reply", url: buildBlueskyPostUrl(did, rkey), content: contextContent };
}

function parseBlueskyMediaUnion(did: string, media: unknown, generatedThumbnailUrl: string | null): Attachment[] {
  if (typeof media !== "object" || media === null) return [];
  const typed = media as { $type?: unknown; images?: unknown; external?: unknown };

  if (typed.$type === "app.bsky.embed.images") return parseBlueskyImages(did, typed.images);
  if (typed.$type === "app.bsky.embed.external") {
    const link = parseBlueskyExternal(did, typed.external, generatedThumbnailUrl);
    return link ? [link] : [];
  }
  if (typed.$type === "app.bsky.embed.video") {
    const video = parseBlueskyVideo(did, media);
    return video ? [video] : [];
  }
  return []; // gallery/etc - not yet observed in production, deferred
}

function parseBlueskyEmbed(
  did: string,
  embed: unknown,
  quoteContent: QuoteContent | null,
  generatedThumbnailUrl: string | null,
  text: string,
): Attachment[] {
  // Only surfaced when the post shows nothing else of its own -- no embed
  // at all, or a bare quote. A post that already carries images/video/an
  // external card is left as-is (matches the Python-side gate).
  const youtubeCard = youtubeLinkFromText(text, generatedThumbnailUrl);

  if (typeof embed !== "object" || embed === null) return youtubeCard ? [youtubeCard] : [];
  const typed = embed as { $type?: unknown; images?: unknown; external?: unknown; record?: unknown; media?: unknown };

  switch (typed.$type) {
    case "app.bsky.embed.images":
      return parseBlueskyImages(did, typed.images);

    case "app.bsky.embed.external": {
      const link = parseBlueskyExternal(did, typed.external, generatedThumbnailUrl);
      return link ? [link] : [];
    }

    case "app.bsky.embed.video": {
      const video = parseBlueskyVideo(did, embed);
      return video ? [video] : [];
    }

    case "app.bsky.embed.record": {
      const quote = parseBlueskyQuote(typed.record, quoteContent);
      const base = quote ? [quote] : [];
      return youtubeCard ? [...base, youtubeCard] : base;
    }

    case "app.bsky.embed.recordWithMedia": {
      // The quote is at embed.record.record, not embed.record directly --
      // same nesting processing/'s quote_resolver.py extracts on the
      // Python side. See the wiki's API Internals page.
      const media = parseBlueskyMediaUnion(did, typed.media, generatedThumbnailUrl);
      const recordWrapper = typed.record as { record?: unknown } | null | undefined;
      const quote = parseBlueskyQuote(recordWrapper?.record, quoteContent);
      return quote ? [...media, quote] : media;
    }

    default:
      // An embed object with no recognised $type (malformed data) shows
      // nothing, so the bare-URL fallback still applies -- same as no
      // embed at all on the Python side.
      return typed.$type == null && youtubeCard ? [youtubeCard] : [];
  }
}

interface MastodonMediaItem {
  type?: unknown;
  url?: unknown;
  preview_url?: unknown;
  description?: unknown;
  meta?: { original?: { width?: unknown; height?: unknown } };
}

function parseMastodonMedia(media: unknown): Attachment[] {
  if (!Array.isArray(media)) return [];

  const result: Attachment[] = [];
  for (const item of media) {
    if (typeof item !== "object" || item === null) continue;
    const m = item as MastodonMediaItem;
    if (!isHttpUrl(m.url)) continue;

    if (m.type === "image") {
      result.push({
        kind: "image",
        thumbnailUrl: isHttpUrl(m.preview_url) ? m.preview_url : m.url,
        fullUrl: m.url,
        alt: nonEmptyString(m.description),
        width: null,
        height: null,
      });
      continue;
    }

    // gifv is a silent looping MP4, not an actual animated GIF - already
    // immediately playable, same as a regular video, just meant to
    // autoplay/loop/mute instead of showing controls.
    if (m.type === "video" || m.type === "gifv") {
      const width = typeof m.meta?.original?.width === "number" ? m.meta.original.width : null;
      const height = typeof m.meta?.original?.height === "number" ? m.meta.original.height : null;
      result.push({
        kind: "video",
        playlistUrl: m.url,
        thumbnailUrl: isHttpUrl(m.preview_url) ? m.preview_url : null,
        isGif: m.type === "gifv",
        width,
        height,
      });
    }
  }
  return result;
}

interface MastodonCard {
  url?: unknown;
  title?: unknown;
  description?: unknown;
  image?: unknown;
  provider_name?: unknown;
}

function parseMastodonCard(card: unknown, generatedThumbnailUrl: string | null): Attachment | null {
  if (typeof card !== "object" || card === null) return null;
  const c = card as MastodonCard;
  if (!isHttpUrl(c.url)) return null;

  // Falls back to processing/'s own og:image fetch (thumbnail_resolver.py)
  // when Mastodon's own server-side card-fetch didn't capture one - never
  // overrides a real source thumbnail. See the wiki's Thumbnail
  // Resolution page.
  const thumbnailUrl = isHttpUrl(c.image)
    ? c.image
    : isHttpUrl(generatedThumbnailUrl)
      ? generatedThumbnailUrl
      : null;

  return {
    kind: "link",
    url: c.url,
    title: nonEmptyString(c.title),
    description: nonEmptyString(c.description),
    thumbnailUrl,
    providerName: nonEmptyString(c.provider_name),
  };
}

function isSensitive(mastodonSensitive: boolean | null, blueskyLabels: unknown): boolean {
  if (mastodonSensitive === true) return true;

  // Selected raw from db.ts deliberately - computing this in SQL
  // (jsonb_array_length) would throw the whole /feed query if any single
  // row's labels.values isn't actually an array, since Jetstream relays
  // whatever a client sent with no schema validation. Defensive here
  // instead, same rule every other field in this file follows.
  if (typeof blueskyLabels === "object" && blueskyLabels !== null) {
    const values = (blueskyLabels as { values?: unknown }).values;
    if (Array.isArray(values) && values.length > 0) return true;
  }
  return false;
}

export function buildAttachments(row: AttachmentSource): AttachmentResult {
  let attachments: Attachment[];
  if (row.source === "bluesky") {
    const contextContent = parseContextContent(row.context_content ?? row.quote_content);
    attachments = parseBlueskyEmbed(row.author_id, row.bluesky_embed, contextContent, row.generated_thumbnail_url, row.text);

    // A reply attachment only applies when the post isn't already a quote
    // -- processing/'s context_dependency.py resolves (and scores) at most
    // one context target per post, quote taking priority, so context_content
    // only ever describes whichever one it actually resolved.
    if (!attachments.some((a) => a.kind === "quote")) {
      const reply = parseBlueskyReply(row.bluesky_reply, contextContent);
      if (reply) attachments = [...attachments, reply];
    }
  } else {
    const card = parseMastodonCard(row.mastodon_card, row.generated_thumbnail_url);
    attachments = [...parseMastodonMedia(row.mastodon_media), ...(card ? [card] : [])];

    // No quote_content fallback here -- that legacy column only ever held
    // Bluesky-resolved content (Mastodon reply/quote-inline resolution
    // didn't exist before context_content), so it's always null on a
    // Mastodon row.
    const context = parseMastodonContext(row.context_kind, row.context_content);
    if (context) attachments = [...attachments, context];
  }

  return { attachments, sensitive: isSensitive(row.mastodon_sensitive, row.bluesky_labels) };
}
