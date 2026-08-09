import type { Attachment } from "../api/types";
import styles from "./QuoteLink.module.css";

type QuoteAttachment = Extract<Attachment, { kind: "quote" }>;

export function QuoteLink({ quote }: { quote: QuoteAttachment }) {
  return (
    <a href={quote.url} target="_blank" rel="noreferrer noopener" className={styles.link}>
      Quotes a post ↗
    </a>
  );
}
