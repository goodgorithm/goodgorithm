import type { FeedPostScores } from "../api/types";
import styles from "./ScoreDetails.module.css";

// Raw numbers, not a natural-language explainer - the project's transparency
// stance is "publish the code/model and hand back the real numbers," not
// "generate a plausible-sounding reason." See the public Algorithm doc.
export function ScoreDetails({ scores }: { scores: FeedPostScores }) {
  return (
    <details className={styles.details}>
      <summary className={styles.summary}>Scores</summary>
      <dl className={styles.grid}>
        <dt className={styles.label}>Sentiment</dt>
        <dd>{scores.sentiment.toFixed(3)}</dd>
        <dt className={styles.label}>Topicality</dt>
        <dd>{scores.topicality.toFixed(3)}</dd>
        <dt className={styles.label}>Base</dt>
        <dd>{scores.base.toFixed(3)}</dd>
        <dt className={styles.label}>Rank</dt>
        <dd>{scores.rank.toFixed(3)}</dd>
      </dl>
    </details>
  );
}
