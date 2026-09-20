import type { Attachment } from "../api/types";
import styles from "./QuoteLink.module.css";

type ContextAttachment = Extract<Attachment, { kind: "quote" | "reply" }>;

const COPY = {
  quote: {
    bareLink: "Quotes a post ↗",
    filtered: "Quoted post hidden (doesn't meet our content guidelines)",
    unavailable: "Quoted post unavailable (deleted or no longer accessible)",
  },
  reply: {
    bareLink: "Replying to a post ↗",
    filtered: "Replied-to post hidden (doesn't meet our content guidelines)",
    unavailable: "Replied-to post unavailable (deleted or no longer accessible)",
  },
} as const;

export function QuoteLink({ quote }: { quote: ContextAttachment }) {
  const { content } = quote;
  const copy = COPY[quote.kind];

  // content is null for Mastodon posts (unreachable, no quotes/replies
  // there yet -- see issue #293), and for any row scored before context
  // resolution shipped - falls back to the original plain-link behavior
  // rather than a broken empty card.
  if (content === null) {
    return (
      <a href={quote.url} target="_blank" rel="noreferrer noopener" className={styles.link}>
        {copy.bareLink}
      </a>
    );
  }

  if (content.status === "unavailable") {
    // Deliberately not a link, for either reason: a deleted/blocked post
    // has nothing useful to click through to, and a filtered one
    // shouldn't be surfaced as clickable at all, consistent with the
    // content filter's precision-over-recall stance.
    const message = content.reason === "filtered" ? copy.filtered : copy.unavailable;
    return <div className={styles.unavailable}>{message}</div>;
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
