import { Logo } from "./Logo";
import styles from "./Wordmark.module.css";

export function Wordmark() {
  return (
    <span className={styles.wordmark} role="img" aria-label="Goodgorithm">
      <Logo size={28} className={styles.mark} />
      <span aria-hidden="true">
        <span className={styles.good}>good</span>
        <span className={styles.gorithm}>gorithm</span>
      </span>
    </span>
  );
}
