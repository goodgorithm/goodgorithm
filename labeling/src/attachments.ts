// Duplicated from api/src/attachments.ts + permalink.ts's buildBlueskyPostUrl
// (same Railway rootDirectory-scoping reason a live shared package isn't
// possible -- see types.ts's header comment). Used only at candidate-creation
// time (the bulk-insert script/route), reading the same raw_posts.raw_json /
// processed_posts.quote_content shape api/'s feed query reads, so a labeller
// sees what the algorithm sees. Kept in sync by hand if api/'s parsing ever
// changes -- same discipline as the api/web type boundary.

import type { Attachment, QuoteContent } from "./types";

export interface AttachmentSource {
  source: "bluesky" | "mastodon";
  author_id: string;
  text: string;
  bluesky_embed: unknown;
  mastodon_media: unknown;
  mastodon_card: unknown;
  quote_content: unknown;
  generated_thumbnail_url: string | null;
}

const BLUESKY_CDN_BASE = "https://cdn.bsky.app/img";
const BLUESKY_VIDEO_CDN_BASE = "https://video.bsky.app/watch";

function blueskyImageUrls(did: string, cid: string): { thumbnailUrl: string; fullUrl: string } {
  return {
    thumbnailUrl: `${BLUESKY_CDN_BASE}/feed_thumbnail/plain/${did}/${cid}@jpeg`,
    fullUrl: `${BLUESKY_CDN_BASE}/feed_fullsize/plain/${did}/${cid}@jpeg`,
  };
}

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

function buildBlueskyPostUrl(did: string, rkey: string): string {
  return `https://bsky.app/profile/${did}/post/${rkey}`;
}

const YOUTUBE_HOSTS = new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"]);
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
  return { kind: "link", url, title: null, description: null, thumbnailUrl: generatedThumbnailUrl, providerName: null };
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
  const thumbnailUrl = sourceThumbnailUrl ?? (isHttpUrl(generatedThumbnailUrl) ? generatedThumbnailUrl : null);
  return {
    kind: "link",
    url: ext.uri,
    title: nonEmptyString(ext.title),
    description: nonEmptyString(ext.description),
    thumbnailUrl,
    providerName: null,
  };
}

interface BlueskyVideoEmbed {
  video?: { ref?: { $link?: unknown } };
  aspectRatio?: { width?: unknown; height?: unknown };
  presentation?: unknown;
}

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

function parseQuoteContent(raw: unknown): QuoteContent | null {
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

function parseBlueskyQuote(record: unknown, quoteContent: QuoteContent | null): Attachment | null {
  if (typeof record !== "object" || record === null) return null;
  const uri = (record as { uri?: unknown }).uri;
  if (typeof uri !== "string") return null;
  const match = AT_URI_PATTERN.exec(uri);
  if (!match) return null;
  const [, did, collection, rkey] = match;
  if (collection !== "app.bsky.feed.post") return null;
  return { kind: "quote", url: buildBlueskyPostUrl(did, rkey), content: quoteContent };
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
  return [];
}

function parseBlueskyEmbed(
  did: string,
  embed: unknown,
  quoteContent: QuoteContent | null,
  generatedThumbnailUrl: string | null,
  text: string,
): Attachment[] {
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
      const media = parseBlueskyMediaUnion(did, typed.media, generatedThumbnailUrl);
      const recordWrapper = typed.record as { record?: unknown } | null | undefined;
      const quote = parseBlueskyQuote(recordWrapper?.record, quoteContent);
      return quote ? [...media, quote] : media;
    }
    default:
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
  const thumbnailUrl = isHttpUrl(c.image) ? c.image : isHttpUrl(generatedThumbnailUrl) ? generatedThumbnailUrl : null;
  return {
    kind: "link",
    url: c.url,
    title: nonEmptyString(c.title),
    description: nonEmptyString(c.description),
    thumbnailUrl,
    providerName: nonEmptyString(c.provider_name),
  };
}

export function buildAttachments(row: AttachmentSource): Attachment[] {
  if (row.source === "bluesky") {
    return parseBlueskyEmbed(
      row.author_id,
      row.bluesky_embed,
      parseQuoteContent(row.quote_content),
      row.generated_thumbnail_url,
      row.text,
    );
  }
  const card = parseMastodonCard(row.mastodon_card, row.generated_thumbnail_url);
  return [...parseMastodonMedia(row.mastodon_media), ...(card ? [card] : [])];
}

export function extractQuoteContent(raw: unknown): QuoteContent | null {
  return parseQuoteContent(raw);
}

// hashtag_bag.py's own extraction is a simple word-boundary regex over raw
// text -- mirrored here rather than imported (Python<->TypeScript boundary,
// same as util/sentiment_model.py's tokenizer note in CLAUDE.md).
const HASHTAG_RE = /#(\w+)/g;

export function extractHashtags(text: string): string[] {
  return [...text.matchAll(HASHTAG_RE)].map((m) => m[1]);
}
