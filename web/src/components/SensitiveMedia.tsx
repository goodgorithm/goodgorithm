import { useState, type ReactNode } from "react";

import styles from "./SensitiveMedia.module.css";

// Shared by ImageGrid, LinkCard, and VideoPlayer - a sensitive-flagged
// post's link-card thumbnail or video can be exactly as graphic as an
// attached image, so all three need the same blur-behind-a-real-button
// treatment, not just inline images.
export function SensitiveMedia({
  sensitive,
  revealLabel = "Show image",
  children,
}: {
  sensitive: boolean;
  revealLabel?: string;
  children: ReactNode;
}) {
  const [revealed, setRevealed] = useState(false);

  if (!sensitive) {
    return <>{children}</>;
  }

  // children stay in the exact same tree position across the reveal toggle
  // -- only the blur class and which button renders change. Conditionally
  // rendering children under a *different* wrapper per branch would make
  // React tear down and remount them on every toggle, which for VideoPlayer
  // would mean losing its hls.js attachment entirely and leaving the video
  // permanently stuck with no error.
  const mediaClassName = revealed ? styles.mediaWrapper : `${styles.mediaWrapper} ${styles.blurred}`;

  return (
    <div className={styles.wrapper}>
      <div className={mediaClassName}>{children}</div>
      {revealed ? (
        <button
          type="button"
          className={styles.hideButton}
          aria-pressed={revealed}
          onClick={() => setRevealed(false)}
        >
          {revealLabel.replace("Show", "Hide")}
        </button>
      ) : (
        <button
          type="button"
          className={styles.revealButton}
          aria-pressed={revealed}
          onClick={() => setRevealed(true)}
        >
          {revealLabel}
        </button>
      )}
    </div>
  );
}
