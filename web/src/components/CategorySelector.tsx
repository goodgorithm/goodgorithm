import { CATEGORIES, CATEGORY_LABELS, type Category } from "../api/types";
import styles from "./CategorySelector.module.css";

// Purely a display order - the canonical CATEGORIES array (api/src/types.ts)
// keeps its research-driven declared order untouched everywhere else (AJV
// validation, processing/'s taxonomy lookup); this is a local sorted copy
// for this component only. Computed once at module scope since
// CATEGORIES/CATEGORY_LABELS are static.
const DISPLAY_ORDER = [...CATEGORIES].sort((a, b) => CATEGORY_LABELS[a].localeCompare(CATEGORY_LABELS[b]));

export function CategorySelector({
  selected,
  onSelect,
}: {
  // Category | null so it type-checks against useCategoryParam's widened
  // state (issue #101's hidden ?category=all) - but onSelect deliberately
  // stays Category-only, since this component must never be capable of
  // producing a null selection itself. No chip ever matches null, so
  // nothing gets the .selected style when the unfiltered feed is active -
  // that's fine, it's not meant to be reachable from here.
  selected: Category | null;
  onSelect: (category: Category) => void;
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
    </div>
  );
}
