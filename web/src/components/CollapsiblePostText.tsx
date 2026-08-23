import { useEffect, useRef, useState } from "react";

import type { Source } from "../api/types";
import { linkify } from "../lib/linkify";
import styles from "./CollapsiblePostText.module.css";

// Rough heuristic for "likely overflows the collapsed line-clamp" - avoids
// showing the toggle on typical short posts. Not exact (depends on line
// width/wrapping), but keeps the common case clean without measuring
// rendered height.
const COLLAPSE_THRESHOLD_CHARS = 400;

export function CollapsiblePostText({
  text,
  source,
  permalink,
}: {
  text: string;
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
  const content = linkify(text, source, permalink);

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
