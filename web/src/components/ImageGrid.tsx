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
              // Always reserve the box so a late-loading image never shifts
              // the feed (Core Web Vitals CLS). Real dimensions when the
              // source gave them; a 16/9 fallback otherwise -- a
              // dimensionless image then letterboxes inside that box
              // (object-fit: contain, see the module CSS) rather than
              // expanding from zero. Ignored for the count2-4 layouts,
              // whose cells are already a fixed height.
              style={{
                aspectRatio:
                  image.width && image.height ? `${image.width} / ${image.height}` : "16 / 9",
              }}
            />
          </a>
        </SensitiveMedia>
      ))}
    </div>
  );
}
