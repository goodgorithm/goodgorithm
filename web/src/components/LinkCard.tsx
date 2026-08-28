import type { Attachment } from "../api/types";
import styles from "./LinkCard.module.css";
import { SensitiveMedia } from "./SensitiveMedia";

type LinkAttachment = Extract<Attachment, { kind: "link" }>;

export function LinkCard({
  link,
  sensitive,
  priority = false,
}: {
  link: LinkAttachment;
  sensitive: boolean;
  // Set only when this is the top feed card's sole media (no image grid) --
  // the thumbnail is then the likely LCP element.
  priority?: boolean;
}) {
  return (
    <a href={link.url} target="_blank" rel="noreferrer noopener" className={styles.card}>
      {link.thumbnailUrl && (
        <SensitiveMedia sensitive={sensitive}>
          <img
            className={styles.thumbnail}
            src={link.thumbnailUrl}
            alt=""
            loading={priority ? "eager" : "lazy"}
            fetchPriority={priority ? "high" : undefined}
          />
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
