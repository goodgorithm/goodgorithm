import { useState, type ReactNode } from "react";

import styles from "./SensitiveMedia.module.css";

// Shared by ImageGrid and LinkCard - a sensitive-flagged post's link-card
// thumbnail can be exactly as graphic as an attached image, so both need
// the same blur-behind-a-real-button treatment, not just inline images.
export function SensitiveMedia({ sensitive, children }: { sensitive: boolean; children: ReactNode }) {
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
        Show image
      </button>
    </div>
  );
}
