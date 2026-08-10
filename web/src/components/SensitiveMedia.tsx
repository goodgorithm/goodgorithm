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

  if (!sensitive || revealed) {
    return <>{children}</>;
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.blurred}>{children}</div>
      <button
        type="button"
        className={styles.revealButton}
        aria-pressed={revealed}
        onClick={() => setRevealed(true)}
      >
        {revealLabel}
      </button>
    </div>
  );
}
