import { CATEGORIES, CATEGORY_LABELS, type Category } from "../api/types";
import styles from "./CategorySelector.module.css";

// Purely a display order - the canonical CATEGORIES array (api/src/types.ts)
// keeps its research-driven declared order untouched everywhere else (AJV
// validation, processing/'s taxonomy lookup); this is a local sorted copy
// for this component only (issue #24). Computed once at module scope since
// CATEGORIES/CATEGORY_LABELS are static.
const DISPLAY_ORDER = [...CATEGORIES].sort((a, b) => CATEGORY_LABELS[a].localeCompare(CATEGORY_LABELS[b]));

export function CategorySelector({
  selected,
  onSelect,
}: {
  selected: Category | null;
  onSelect: (category: Category | null) => void;
}) {
  return (
    <div className={styles.grid}>
      {DISPLAY_ORDER.map((category) => (
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
  );
}
