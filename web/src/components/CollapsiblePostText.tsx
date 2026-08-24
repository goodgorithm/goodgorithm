import { Fragment, useEffect, useRef, useState } from "react";

import type { CustomEmoji, Source } from "../api/types";
import { renderEmojiShortcodes } from "../lib/emoji";
import { linkify } from "../lib/linkify";
import styles from "./CollapsiblePostText.module.css";

// Rough heuristic for "likely overflows the collapsed line-clamp" - avoids
// showing the toggle on typical short posts. Not exact (depends on line
// width/wrapping), but keeps the common case clean without measuring
// rendered height.
const COLLAPSE_THRESHOLD_CHARS = 400;

export function CollapsiblePostText({
  text,
  emojis,
  source,
  permalink,
}: {
  text: string;
  emojis: CustomEmoji[];
  source: Source;
  permalink: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  // Tracks the prior render's expanded value so the effect below can tell
  // "just collapsed" (true -> false) apart from "mounted already
  // collapsed" (false on first render too) - only the former should ever
  // move the scroll position.
  const wasExpandedRef = useRef(false);
  // Emoji substitution runs first, then linkify only over the plain-text
  // segments it leaves behind (an emoji <img> has no URLs/hashtags of its
  // own to find) - each segment gets its own keyed Fragment so linkify's
  // own internal key counter (which restarts at 0 per call) never collides
  // with another segment's, since React only requires key uniqueness among
  // siblings, not globally (issue #77).
  const content = renderEmojiShortcodes(text, emojis).map((segment, i) => (
    <Fragment key={i}>{typeof segment === "string" ? linkify(segment, source, permalink) : segment}</Fragment>
  ));

  useEffect(() => {
    // Collapsing shrinks the post's height, which pulls everything below
    // it upward - if the post scrolled out of view above the viewport as
    // a result, the reader lands with no visible cue what happened (issue
    // #60). Only correct for that case (top < 0, scrolled past) rather
    // than unconditionally scrolling on every collapse, so this stays a
    // no-op when the reader was already looking at the top of the post.
    if (wasExpandedRef.current && !expanded) {
      const el = containerRef.current;
      if (el && el.getBoundingClientRect().top < 0) {
        el.scrollIntoView({ block: "start" });
      }
    }
    wasExpandedRef.current = expanded;
  }, [expanded]);

  if (text.length <= COLLAPSE_THRESHOLD_CHARS) {
    return <p className={styles.text}>{content}</p>;
  }

  return (
    <div ref={containerRef}>
      <p className={expanded ? styles.text : `${styles.text} ${styles.collapsed}`}>{content}</p>
      <button type="button" className={styles.toggle} onClick={() => setExpanded((e) => !e)}>
        {expanded ? "Show less" : "Show more"}
      </button>
    </div>
  );
}
