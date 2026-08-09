import type { Attachment } from "../api/types";
import styles from "./ImageGrid.module.css";
import { SensitiveMedia } from "./SensitiveMedia";

type ImageAttachment = Extract<Attachment, { kind: "image" }>;

export function ImageGrid({ images, sensitive }: { images: ImageAttachment[]; sensitive: boolean }) {
  if (images.length === 0) return null;

  const shown = images.slice(0, 4);
  const countClass = styles[`count${shown.length}` as keyof typeof styles];

  return (
    <div className={`${styles.grid} ${countClass}`}>
      {shown.map((image) => (
        <SensitiveMedia key={image.thumbnailUrl} sensitive={sensitive}>
          <a href={image.fullUrl} target="_blank" rel="noreferrer noopener" className={styles.imageLink}>
            <img
              className={styles.image}
              src={image.thumbnailUrl}
              alt={image.alt ?? ""}
              loading="lazy"
              style={
                image.width && image.height ? { aspectRatio: `${image.width} / ${image.height}` } : undefined
              }
            />
          </a>
        </SensitiveMedia>
      ))}
    </div>
  );
}
