import type { ReactNode } from "react";

import type { Source } from "../api/types";

// Trailing punctuation a URL commonly ends a sentence with, but that was
// never part of the URL itself (e.g. "check this out: https://example.com."
// shouldn't swallow the period into the link).
const TRAILING_PUNCTUATION = /[).,!?;:'"]+$/;

function hashtagUrl(tag: string, source: Source, permalink: string): string {
  if (source === "bluesky") {
    return `https://bsky.app/search?q=${encodeURIComponent(`#${tag}`)}`;
  }
  // Mastodon: derive the origin instance from the post's own permalink
  // (https://{instance}/@handle/id) - no other per-post instance field is
  // exposed to web/, and every instance serves the same public /tags/ path.
  try {
    return `${new URL(permalink).origin}/tags/${tag}`;
  } catch {
    return `https://${permalink}/tags/${tag}`;
  }
}

// Same regex-tokenizer shape as markdown.tsx's renderInline - builds React
// nodes directly from matched substrings rather than ever touching
// dangerouslySetInnerHTML, so this adds no new XSS surface over plain text.
export function linkify(text: string, source: Source, permalink: string): ReactNode[] {
  const pattern = /(https?:\/\/\S+)|(#\w+)/g;
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    if (match[1] !== undefined) {
      const trailingMatch = match[1].match(TRAILING_PUNCTUATION);
      const trailing = trailingMatch ? trailingMatch[0] : "";
      const url = trailing ? match[1].slice(0, -trailing.length) : match[1];
      nodes.push(
        <a key={key++} href={url} target="_blank" rel="noreferrer noopener">
          {url}
        </a>,
      );
      if (trailing) nodes.push(trailing);
    } else {
      const tag = match[2].slice(1);
      nodes.push(
        <a key={key++} href={hashtagUrl(tag, source, permalink)} target="_blank" rel="noreferrer noopener">
          {match[2]}
        </a>,
      );
    }

    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}
