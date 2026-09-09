import { useEffect, useRef, useState } from "react";

import type { Attachment } from "../api/types";
import styles from "./ImageGrid.module.css";
import { SensitiveMedia } from "./SensitiveMedia";

type ImageAttachment = Extract<Attachment, { kind: "image" }>;

// Bluesky's cdn.bsky.app/img/feed_thumbnail transform is generated on
// demand: the first request for a given image can take several seconds
// while every request after it is edge-warm. If a load hits that cold path
// and the browser gives up (image timeout, backgrounded tab, connection
// blip) the slot is stuck showing the broken-image glyph until the element
// re-renders. ImageCell escalates a failed load instead: after a short
// pause retry the thumbnail against the now-likely-warm edge (the r= param
// busts only the *browser's* cache -- Bluesky's CDN ignores unknown query
// params), then the independently-cached fullsize transform, then a
// tap-to-open placeholder. The <a href={fullUrl}> wrapper opens the image
// in a new tab regardless of which state the cell is in.
const RETRY_DELAY_MS = 1000;

function withCacheBust(url: string): string {
  try {
    const parsed = new URL(url);
    parsed.searchParams.set("r", "1");
    return parsed.toString();
  } catch {
    return url;
  }
}

type LoadStage = "thumb" | "thumb-retry" | "full" | "failed";

function ImageCell({
  image,
  sensitive,
  eager,
}: {
  image: ImageAttachment;
  sensitive: boolean;
  eager: boolean;
}) {
  const [stage, setStage] = useState<LoadStage>("thumb");
  const retryTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => () => clearTimeout(retryTimer.current), []);

  function handleError() {
    if (stage === "thumb") {
      // Give the cold transform a moment to finish server-side, then retry
      // the (now warm) edge rather than racing the same slow path again.
      retryTimer.current = setTimeout(() => setStage("thumb-retry"), RETRY_DELAY_MS);
    } else if (stage === "thumb-retry") {
      setStage("full");
    } else if (stage === "full") {
      setStage("failed");
    }
  }

  const src =
    stage === "thumb-retry"
      ? withCacheBust(image.thumbnailUrl)
      : stage === "full"
        ? image.fullUrl
        : image.thumbnailUrl;

  // Always reserve the box so a late-loading image never shifts the feed
  // (Core Web Vitals CLS). Real dimensions when the source gave them; a
  // 16/9 fallback otherwise -- a dimensionless image then letterboxes
  // inside that box (object-fit: contain, see the module CSS) rather than
  // expanding from zero. Ignored for the count2-4 layouts, whose cells are
  // already a fixed height.
  const boxStyle = {
    aspectRatio: image.width && image.height ? `${image.width} / ${image.height}` : "16 / 9",
  };

  return (
    <SensitiveMedia sensitive={sensitive}>
      <a href={image.fullUrl} target="_blank" rel="noreferrer noopener" className={styles.imageLink}>
        {stage === "failed" ? (
          <div className={styles.placeholder} style={boxStyle}>
            Image didn't load — tap to open ↗
          </div>
        ) : (
          <img
            className={styles.image}
            src={src}
            alt={image.alt ?? ""}
            loading={eager ? "eager" : "lazy"}
            fetchPriority={eager ? "high" : undefined}
            onError={handleError}
            style={boxStyle}
          />
        )}
      </a>
    </SensitiveMedia>
  );
}

export function ImageGrid({
  images,
  sensitive,
  priority = false,
}: {
  images: ImageAttachment[];
  sensitive: boolean;
  // Set only for the top feed card's grid: its first image is the likely
  // LCP element, so it loads eagerly at high priority instead of lazy.
  priority?: boolean;
}) {
  if (images.length === 0) return null;

  const shown = images.slice(0, 4);
  const countClass = styles[`count${shown.length}` as keyof typeof styles];

  return (
    <div className={`${styles.grid} ${countClass}`}>
      {shown.map((image, i) => (
        <ImageCell
          key={image.thumbnailUrl}
          image={image}
          sensitive={sensitive}
          // The very first image of a priority grid is the LCP candidate.
          eager={priority && i === 0}
        />
      ))}
    </div>
  );
}
