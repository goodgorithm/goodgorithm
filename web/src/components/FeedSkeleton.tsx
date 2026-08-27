import styles from "./FeedSkeleton.module.css";

// First-paint placeholder for the feed. Rendered while the initial page is
// loading, in place of the plain "Loading feed…" line, so a large
// contentful element is on screen early rather than after the JS bundle +
// a live feed fetch (Core Web Vitals LCP -- see the wiki's Web Internals
// page). aria-hidden: it carries no information, and index.html's static
// shell already provides an sr-only role="status" during the pre-hydration
// window.
const CARD_COUNT = 3;

function SkeletonCard() {
  return (
    <div className={styles.card}>
      <div className={styles.row}>
        <div className={`${styles.bar} ${styles.pill}`} />
        <div className={`${styles.bar} ${styles.short}`} />
        <div className={`${styles.bar} ${styles.time}`} />
      </div>
      <div className={`${styles.bar} ${styles.line}`} />
      <div className={`${styles.bar} ${styles.line}`} />
      <div className={`${styles.bar} ${styles.line} ${styles.w60}`} />
      <div className={styles.foot}>
        <div className={`${styles.bar} ${styles.footBar}`} />
        <div className={`${styles.bar} ${styles.footBar}`} />
      </div>
    </div>
  );
}

export function FeedSkeleton() {
  return (
    <div aria-hidden="true">
      {Array.from({ length: CARD_COUNT }, (_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
