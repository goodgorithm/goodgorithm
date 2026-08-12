import { useState } from "react";

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
  const content = linkify(text, source, permalink);

  if (text.length <= COLLAPSE_THRESHOLD_CHARS) {
    return <p className={styles.text}>{content}</p>;
  }

  return (
    <div>
      <p className={expanded ? styles.text : `${styles.text} ${styles.collapsed}`}>{content}</p>
      <button type="button" className={styles.toggle} onClick={() => setExpanded((e) => !e)}>
        {expanded ? "Show less" : "Show more"}
      </button>
    </div>
  );
}
