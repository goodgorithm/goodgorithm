import type { ReactNode } from "react";

import type { CustomEmoji } from "../api/types";
import styles from "./emoji.module.css";

const SHORTCODE_RE = /:([a-zA-Z0-9_]+):/g;

// Substitutes Mastodon custom-emoji shortcodes (issue #77, e.g. a display
// name of "Volodymyr Zelenskyy :bot:") with the real inline image
// Mastodon's own client would show, using the emojis array that already
// ships in raw_json for free - no extra API call, just the browser
// fetching the image directly, same as avatars/media already do. A
// `:word:`-shaped span that isn't a real shortcode in *this* post's/
// account's own emojis array (ordinary text using colons) is left as
// plain text untouched - same "don't touch what you can't resolve"
// caution as linkify.tsx leaving non-matching text alone.
export function renderEmojiShortcodes(text: string, emojis: CustomEmoji[]): (string | ReactNode)[] {
  if (emojis.length === 0) return [text];
  const byShortcode = new Map(emojis.map((e) => [e.shortcode, e]));

  const nodes: (string | ReactNode)[] = [];
  let lastIndex = 0;
  let key = 0;
  let match: RegExpExecArray | null;

  while ((match = SHORTCODE_RE.exec(text)) !== null) {
    const emoji = byShortcode.get(match[1]);
    if (!emoji) continue;

    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    nodes.push(<img key={key++} className={styles.emoji} src={emoji.url} alt={`:${match[1]}:`} />);
    lastIndex = SHORTCODE_RE.lastIndex;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}
