import { Markdown } from "../lib/markdown";
import styles from "./ContentPage.module.css";

// Generic static-content page - takes markdown source directly rather
// than importing a specific content file, so it stays reusable for any
// future content page instead of getting copy-pasted per page.
export function ContentPage({ source, onBack }: { source: string; onBack: () => void }) {
  return (
    <article className={styles.page}>
      <button type="button" className={styles.back} onClick={onBack}>
        ← Back to feed
      </button>
      <div className={styles.content}>
        <Markdown source={source} />
      </div>
    </article>
  );
}
