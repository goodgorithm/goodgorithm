import type { Attachment } from "../api/types";
import styles from "./QuoteLink.module.css";

type QuoteAttachment = Extract<Attachment, { kind: "quote" }>;

export function QuoteLink({ quote }: { quote: QuoteAttachment }) {
  const { content } = quote;

  // content is null for Mastodon posts (unreachable, no quotes there),
  // and for any row scored before quote resolution shipped - falls back
  // to the original plain-link behavior rather than a broken empty card.
  if (content === null) {
    return (
      <a href={quote.url} target="_blank" rel="noreferrer noopener" className={styles.link}>
        Quotes a post ↗
      </a>
    );
  }

  if (content.status === "unavailable") {
    // Deliberately not a link, for either reason: a deleted/blocked post
    // has nothing useful to click through to, and a filtered one
    // shouldn't be surfaced as clickable at all, consistent with the
    // content filter's precision-over-recall stance.
    return <div className={styles.unavailable}>Quoted post unavailable</div>;
  }

  const name = content.author.displayName ?? content.author.handle ?? "Someone";

  return (
    <a href={quote.url} target="_blank" rel="noreferrer noopener" className={styles.card}>
      <div className={styles.header}>
        {content.author.avatarUrl && (
          <img className={styles.avatar} src={content.author.avatarUrl} alt="" loading="lazy" />
        )}
        <span className={styles.author}>{name}</span>
      </div>
      <div className={styles.text}>{content.text}</div>
    </a>
  );
}
