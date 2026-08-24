import type { FeedPostScores } from "../api/types";
import { sentimentFraction, type RelativeFractions } from "../lib/scoreScale";
import styles from "./ScoreDetails.module.css";

// Fraction (0-1) is the primary signal - bar length, not color, carries the
// magnitude, so it reads regardless of color perception. Flat accent fill
// (not a gradient) matches how --color-accent already means
// "positive/active" everywhere else in the app.
function ScoreBar({ fraction }: { fraction: number }) {
  return (
    <span className={styles.barTrack}>
      <span className={styles.barFill} style={{ width: `${fraction * 100}%` }} />
    </span>
  );
}

// Raw numbers in the expanded view, not a natural-language explainer - the
// project's transparency stance is "publish the code/model and hand back
// the real numbers," not "generate a plausible-sounding reason." Every
// number gets its own bar so it's anchored to a visual scale instead of
// floating alone - that's the part a lone number never communicated.
export function ScoreDetails({
  scores,
  relative,
}: {
  scores: FeedPostScores;
  relative: RelativeFractions;
}) {
  const sentiment = sentimentFraction(scores.sentiment);

  return (
    <details className={styles.details}>
      <summary
        className={styles.summary}
        title={`Sentiment ${scores.sentiment.toFixed(2)} · Topicality ${scores.topicality.toFixed(2)} · Base ${scores.base.toFixed(2)} · Rank ${scores.rank.toFixed(2)}`}
      >
        <span className={styles.miniBar}>
          <ScoreBar fraction={sentiment} />
        </span>
        <span>Scores</span>
      </summary>
      <div className={styles.rows}>
        <div className={styles.row}>
          <span className={styles.rowLabel}>Sentiment</span>
          <ScoreBar fraction={sentiment} />
          <span className={styles.rowValue}>{scores.sentiment.toFixed(2)}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabel}>
            Topicality
            <small>vs. this batch</small>
          </span>
          <ScoreBar fraction={relative.topicality} />
          <span className={styles.rowValue}>{scores.topicality.toFixed(2)}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabel}>
            Base
            <small>vs. this batch</small>
          </span>
          <ScoreBar fraction={relative.base} />
          <span className={styles.rowValue}>{scores.base.toFixed(2)}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.rowLabel}>
            Rank
            <small>vs. this batch</small>
          </span>
          <ScoreBar fraction={relative.rank} />
          <span className={styles.rowValue}>{scores.rank.toFixed(2)}</span>
        </div>
      </div>
      {/* A plain external link, not client-side routing - algorithm
          mechanics live on the GitHub Wiki, not in this app. */}
      <a
        className={styles.algorithmLink}
        href="https://github.com/goodgorithm/goodgorithm/wiki/Algorithm"
        target="_blank"
        rel="noreferrer noopener"
      >
        How these are calculated →
      </a>
    </details>
  );
}
