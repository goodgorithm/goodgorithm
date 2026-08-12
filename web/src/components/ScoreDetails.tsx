import type { FeedPostScores } from "../api/types";
import { sentimentFraction } from "../lib/scoreRing";
import styles from "./ScoreDetails.module.css";

// Percentage-ring geometry: radius chosen so the circumference is exactly
// 100, so a fraction in [0,1] maps directly to stroke-dasharray units with
// no extra scaling math.
const RADIUS = 15.9155;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

// Arc length (not color) is the primary signal - colorblind-safe by
// construction, since "how much of the ring is filled" doesn't depend on
// hue perception. The single accent-color fill (vs. a color gradient)
// matches how the rest of the app already uses --color-accent for
// "positive/active," and avoids the contrast risk a multi-step gradient
// would carry at low values.
function ScoreRing({ fraction }: { fraction: number }) {
  const dash = fraction * CIRCUMFERENCE;
  return (
    <svg viewBox="0 0 36 36" className={styles.ring} aria-hidden="true">
      <circle cx="18" cy="18" r={RADIUS} className={styles.ringTrack} />
      <circle
        cx="18"
        cy="18"
        r={RADIUS}
        className={styles.ringFill}
        strokeDasharray={`${dash} ${CIRCUMFERENCE}`}
        transform="rotate(-90 18 18)"
      />
    </svg>
  );
}

// Raw numbers in the expanded view, not a natural-language explainer - the
// project's transparency stance is "publish the code/model and hand back
// the real numbers," not "generate a plausible-sounding reason." The ring
// is the at-a-glance layer on top of that, not a replacement for it.
export function ScoreDetails({ scores }: { scores: FeedPostScores }) {
  return (
    <details className={styles.details}>
      <summary
        className={styles.summary}
        title={`Sentiment ${scores.sentiment.toFixed(2)} · Topicality ${scores.topicality.toFixed(2)} · Base ${scores.base.toFixed(2)} · Rank ${scores.rank.toFixed(2)}`}
      >
        <ScoreRing fraction={sentimentFraction(scores.sentiment)} />
        <span>Scores</span>
      </summary>
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
      <a className={styles.algorithmLink} href="/algorithm">
        How these are calculated →
      </a>
    </details>
  );
}
