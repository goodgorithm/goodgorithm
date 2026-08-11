import { CATEGORIES, CATEGORY_LABELS, type Category } from "../api/types";
import styles from "./CategorySelector.module.css";

export function CategorySelector({
  selected,
  onSelect,
}: {
  selected: Category | null;
  onSelect: (category: Category | null) => void;
}) {
  return (
    <div className={styles.row}>
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
  );
}
