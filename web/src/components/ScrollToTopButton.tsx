import { useEffect, useState } from "react";

import styles from "./ScrollToTopButton.module.css";

// Threshold before showing, so it doesn't clutter a page that's barely
// scrolled - roughly "a couple of post cards down".
const SHOW_AFTER_PX = 600;

// Pure viewport scroll, nothing else - deliberately distinct from Feed's
// "Back to top" button (Feed.tsx/.module.css's .backToTop), which resets
// the anti-repeat cursor and refetches the top of the ranked feed. This
// one never touches feed/query state, just window.scrollTo. Rendered at
// the App level (like UpdatePrompt) since it's a page-wide utility, not
// feed-specific - mobile browsers already scroll to top on a status-bar
// tap, so this is really filling a desktop gap, but there's no reason to
// hide it on mobile too.
export function ScrollToTopButton() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > SHOW_AFTER_PX);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  if (!visible) return null;

  return (
    <button
      type="button"
      className={styles.button}
      aria-label="Scroll to top"
      onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M12 19V5M12 5L5 12M12 5L19 12"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}
