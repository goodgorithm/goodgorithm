import type { FeedPost } from "../api/types";
import { CollapsiblePostText } from "./CollapsiblePostText";
import { EntityTags } from "./EntityTags";
import styles from "./PostCard.module.css";
import { PostAttachments } from "./PostAttachments";
import { RelativeTime } from "./RelativeTime";
import { ScoreDetails } from "./ScoreDetails";
import { SourceBadge } from "./SourceBadge";

export function PostCard({ post }: { post: FeedPost }) {
  return (
    <article className={styles.card}>
      <div className={styles.header}>
        <SourceBadge source={post.source} />
        {post.author.avatar_url && (
          <img
            className={styles.avatar}
            src={post.author.avatar_url}
            alt={post.author.display_name ?? ""}
          />
        )}
        {post.author.display_name && (
          <span className={styles.authorName}>{post.author.display_name}</span>
        )}
        <RelativeTime date={post.created_at} />
      </div>

      <CollapsiblePostText text={post.text} />
      <EntityTags entities={post.entities} />
      <PostAttachments post={post} />

      <div className={styles.footer}>
        {post.permalink && (
          <a
            className={styles.permalink}
            href={post.permalink}
            target="_blank"
            rel="noreferrer noopener"
          >
            View original ↗
          </a>
        )}
        <ScoreDetails scores={post.scores} />
      </div>
    </article>
  );
}
