import missionSource from "../content/mission.md?raw";
import { Markdown } from "../lib/markdown";
import styles from "./MissionPage.module.css";

export function MissionPage({ onBack }: { onBack: () => void }) {
  return (
    <article className={styles.page}>
      <button type="button" className={styles.back} onClick={onBack}>
        ← Back to feed
      </button>
      <div className={styles.content}>
        <Markdown source={missionSource} />
      </div>
    </article>
  );
}
