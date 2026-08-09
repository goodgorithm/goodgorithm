import type { Attachment } from "../api/types";
import styles from "./LinkCard.module.css";
import { SensitiveMedia } from "./SensitiveMedia";

type LinkAttachment = Extract<Attachment, { kind: "link" }>;

export function LinkCard({ link, sensitive }: { link: LinkAttachment; sensitive: boolean }) {
  return (
    <a href={link.url} target="_blank" rel="noreferrer noopener" className={styles.card}>
      {link.thumbnailUrl && (
        <SensitiveMedia sensitive={sensitive}>
          <img className={styles.thumbnail} src={link.thumbnailUrl} alt="" loading="lazy" />
        </SensitiveMedia>
      )}
      <div className={styles.body}>
        {link.title && <div className={styles.title}>{link.title}</div>}
        {link.description && <div className={styles.description}>{link.description}</div>}
        {link.providerName && <div className={styles.provider}>{link.providerName}</div>}
      </div>
    </a>
  );
}
