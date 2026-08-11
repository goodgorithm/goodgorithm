import { useEffect, useRef, useState } from "react";

import { CATEGORIES, CATEGORY_LABELS, type Category } from "../api/types";
import styles from "./CategorySelector.module.css";

export function CategorySelector({
  selected,
  onSelect,
}: {
  selected: Category | null;
  onSelect: (category: Category | null) => void;
}) {
  const rowRef = useRef<HTMLDivElement>(null);
  // The row silently overflows on narrow viewports with no visible
  // scrollbar (deliberately hidden for a cleaner chip look) - without
  // these, "Full feed" and the last few categories are invisible with no
  // hint more content exists off-screen. Found live on staging.
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  useEffect(() => {
    const el = rowRef.current;
    if (!el) return;

    const updateScrollState = () => {
      setCanScrollLeft(el.scrollLeft > 4);
      setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
    };

    updateScrollState();
    el.addEventListener("scroll", updateScrollState, { passive: true });
    window.addEventListener("resize", updateScrollState);
    return () => {
      el.removeEventListener("scroll", updateScrollState);
      window.removeEventListener("resize", updateScrollState);
    };
  }, []);

  return (
    <div className={styles.wrapper}>
      <div className={styles.row} ref={rowRef}>
        {CATEGORIES.map((category) => (
          <button
            key={category}
            type="button"
            className={selected === category ? `${styles.chip} ${styles.selected}` : styles.chip}
            onClick={() => onSelect(category)}
          >
            {CATEGORY_LABELS[category]}
          </button>
        ))}
        {/* Deliberately last and visually de-emphasized (dashed border, muted
            color, never accent-colored even when active) - a category should
            feel like the default pick, not the unfiltered feed. */}
        <button
          type="button"
          className={selected === null ? `${styles.fullFeed} ${styles.fullFeedSelected}` : styles.fullFeed}
          onClick={() => onSelect(null)}
        >
          Full feed
        </button>
      </div>
      {canScrollLeft && (
        <div className={`${styles.fade} ${styles.fadeLeft}`} aria-hidden="true">
          <span className={styles.chevron}>‹</span>
        </div>
      )}
      {canScrollRight && (
        <div className={`${styles.fade} ${styles.fadeRight}`} aria-hidden="true">
          <span className={styles.chevron}>›</span>
        </div>
      )}
    </div>
  );
}
