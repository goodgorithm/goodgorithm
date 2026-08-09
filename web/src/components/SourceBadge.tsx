import type { Source } from "../api/types";
import styles from "./SourceBadge.module.css";

const LABELS: Record<Source, string> = {
  bluesky: "Bluesky",
  mastodon: "Mastodon",
};

export function SourceBadge({ source }: { source: Source }) {
  return <span className={styles.badge}>{LABELS[source]}</span>;
}
