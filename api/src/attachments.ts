import { buildBlueskyPostUrl } from "./permalink";

export type Attachment =
  | {
      kind: "image";
      thumbnailUrl: string;
      fullUrl: string;
      alt: string | null;
      width: number | null;
      height: number | null;
    }
  | {
      kind: "link";
      url: string;
      title: string | null;
      description: string | null;
      thumbnailUrl: string | null;
      providerName: string | null;
    }
  | {
      kind: "video";
      playlistUrl: string;
      thumbnailUrl: string | null;
      isGif: boolean;
      width: number | null;
      height: number | null;
    }
  | { kind: "quote"; url: string };

export interface AttachmentSource {
  source: "bluesky" | "mastodon";
  author_id: string;
  bluesky_embed: unknown;
  mastodon_media: unknown;
  mastodon_card: unknown;
  mastodon_sensitive: boolean | null;
  bluesky_labels: unknown;
}

export interface AttachmentResult {
  attachments: Attachment[];
  sensitive: boolean;
}

const BLUESKY_CDN_BASE = "https://cdn.bsky.app/img";
const BLUESKY_VIDEO_CDN_BASE = "https://video.bsky.app/watch";

// Verified directly against production data: both feed_thumbnail and
// feed_fullsize resolve for real did+cid pairs from both post images and
// link-card thumbnails (different embed fields, same blob-storage
// mechanism), no auth needed.
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

function parseBlueskyExternal(did: string, external: unknown): Attachment | null {
  if (typeof external !== "object" || external === null) return null;
  const ext = external as BlueskyExternal;
  if (!isHttpUrl(ext.uri)) return null;

  const cid = ext.thumb?.ref?.$link;
  const thumbnailUrl = typeof cid === "string" ? blueskyImageUrls(did, cid).thumbnailUrl : null;

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
// constructable client-side from did+videoCid, confirmed against several
// independent open-source Bluesky client implementations - same pattern
// as blueskyImageUrls above, no AppView call needed. thumbnailUrl is only
// available via the AppView's hydrated view shape, not the raw record -
// not worth a network call just for a poster frame, ships null for now.
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

function parseBlueskyQuote(record: unknown): Attachment | null {
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

  return { kind: "quote", url: buildBlueskyPostUrl(did, rkey) };
}

function parseBlueskyMediaUnion(did: string, media: unknown): Attachment[] {
  if (typeof media !== "object" || media === null) return [];
  const typed = media as { $type?: unknown; images?: unknown; external?: unknown };

  if (typed.$type === "app.bsky.embed.images") return parseBlueskyImages(did, typed.images);
  if (typed.$type === "app.bsky.embed.external") {
    const link = parseBlueskyExternal(did, typed.external);
    return link ? [link] : [];
  }
  if (typed.$type === "app.bsky.embed.video") {
    const video = parseBlueskyVideo(did, media);
    return video ? [video] : [];
  }
  return []; // gallery/etc - not yet observed in production, deferred
}

function parseBlueskyEmbed(did: string, embed: unknown): Attachment[] {
  if (typeof embed !== "object" || embed === null) return [];
  const typed = embed as { $type?: unknown; images?: unknown; external?: unknown; record?: unknown; media?: unknown };

  switch (typed.$type) {
    case "app.bsky.embed.images":
      return parseBlueskyImages(did, typed.images);

    case "app.bsky.embed.external": {
      const link = parseBlueskyExternal(did, typed.external);
      return link ? [link] : [];
    }

    case "app.bsky.embed.video": {
      const video = parseBlueskyVideo(did, embed);
      return video ? [video] : [];
    }

    case "app.bsky.embed.record": {
      const quote = parseBlueskyQuote(typed.record);
      return quote ? [quote] : [];
    }

    case "app.bsky.embed.recordWithMedia": {
      // Nesting confirmed against a real row: the quote is at
      // embed.record.record, not embed.record directly.
      const media = parseBlueskyMediaUnion(did, typed.media);
      const recordWrapper = typed.record as { record?: unknown } | null | undefined;
      const quote = parseBlueskyQuote(recordWrapper?.record);
      return quote ? [...media, quote] : media;
    }

    default:
      return [];
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

function parseMastodonCard(card: unknown): Attachment | null {
  if (typeof card !== "object" || card === null) return null;
  const c = card as MastodonCard;
  if (!isHttpUrl(c.url)) return null;

  return {
    kind: "link",
    url: c.url,
    title: nonEmptyString(c.title),
    description: nonEmptyString(c.description),
    thumbnailUrl: isHttpUrl(c.image) ? c.image : null,
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
    attachments = parseBlueskyEmbed(row.author_id, row.bluesky_embed);
  } else {
    const card = parseMastodonCard(row.mastodon_card);
    attachments = [...parseMastodonMedia(row.mastodon_media), ...(card ? [card] : [])];
  }

  return { attachments, sensitive: isSensitive(row.mastodon_sensitive, row.bluesky_labels) };
}
