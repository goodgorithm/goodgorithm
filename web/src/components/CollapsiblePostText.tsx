import { useState } from "react";

import styles from "./CollapsiblePostText.module.css";

// Rough heuristic for "likely overflows the collapsed line-clamp" - avoids
// showing the toggle on typical short posts. Not exact (depends on line
// width/wrapping), but keeps the common case clean without measuring
// rendered height.
const COLLAPSE_THRESHOLD_CHARS = 400;

export function CollapsiblePostText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);

  if (text.length <= COLLAPSE_THRESHOLD_CHARS) {
    return <p className={styles.text}>{text}</p>;
  }

  return (
    <div>
      <p className={expanded ? styles.text : `${styles.text} ${styles.collapsed}`}>{text}</p>
      <button type="button" className={styles.toggle} onClick={() => setExpanded((e) => !e)}>
        {expanded ? "Show less" : "Show more"}
      </button>
    </div>
  );
}
