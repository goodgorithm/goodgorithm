import type { CustomEmoji } from "./types";

export type { CustomEmoji } from "./types";

// shortcode/url come verbatim from arbitrary Mastodon instances' raw_json -
// cheaper and safer to validate here once than to trust every downstream
// renderer never to trip on a malformed entry.
function isHttpUrl(url: unknown): url is string {
  if (typeof url !== "string") return false;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

interface RawCustomEmoji {
  shortcode?: unknown;
  url?: unknown;
}

// Mastodon's raw_json already carries account.emojis (for display_name)
// and the status's own top-level emojis (for post text) verbatim - no
// resolution call needed, just shape validation, same defensive style as
// attachments.ts's parseMastodonMedia. Bluesky rows have no emojis concept
// at all - db.ts never selects a Bluesky equivalent, so `raw` is always
// `null`/`undefined` for those and this returns `[]`. See issue #77.
export function buildEmojis(raw: unknown): CustomEmoji[] {
  if (!Array.isArray(raw)) return [];

  const result: CustomEmoji[] = [];
  for (const item of raw) {
    if (typeof item !== "object" || item === null) continue;
    const e = item as RawCustomEmoji;
    if (typeof e.shortcode !== "string" || e.shortcode === "" || !isHttpUrl(e.url)) continue;
    result.push({ shortcode: e.shortcode, url: e.url });
  }
  return result;
}
