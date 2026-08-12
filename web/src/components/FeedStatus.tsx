import { CATEGORY_LABELS, type Category } from "../api/types";
import styles from "./FeedStatus.module.css";

export function FeedLoading() {
  return <p role="status">Loading feed…</p>;
}

export function FeedEmpty({
  category,
  onShowFullFeed,
}: {
  category: Category | null;
  onShowFullFeed: () => void;
}) {
  if (category === null) {
    return <p role="status">No posts yet.</p>;
  }

  return (
    <div role="status" className={styles.notice}>
      <p>No posts in {CATEGORY_LABELS[category]} yet.</p>
      <button type="button" className={styles.action} onClick={onShowFullFeed}>
        Show full feed
      </button>
    </div>
  );
}

// Deliberately never shows stale/cached posts here - a live-ranked feed
// silently serving old data offline would misrepresent itself. See the
// no-runtimeCaching decision in vite.config.ts.
export function FeedError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className={styles.notice}>
      <p>Something went wrong loading the feed.</p>
      <p className={styles.detail}>
        <small>{message}</small>
      </p>
      <button type="button" className={styles.action} onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}
