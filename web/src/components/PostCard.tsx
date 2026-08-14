import type { FeedPost } from "../api/types";
import type { RelativeFractions } from "../lib/scoreScale";
import { CollapsiblePostText } from "./CollapsiblePostText";
import { EntityTags } from "./EntityTags";
import styles from "./PostCard.module.css";
import { PostAttachments } from "./PostAttachments";
import { RelativeTime } from "./RelativeTime";
import { ScoreDetails } from "./ScoreDetails";
import { SourceBadge } from "./SourceBadge";

// Deep-links to the moderation-report issue template (issue #7), pre-filled
// with this post's permalink under the template's own "Post or account"
// heading -- GitHub's standard query-param pre-fill for .md-style issue
// templates, no backend needed. The reporter still fills in "What's wrong"
// themselves; a moderator reviews and acts by hand (see the Content
// Policy wiki page).
function reportUrl(permalink: string): string {
  const body = `## Post or account\n\n${permalink}\n\n## What's wrong\n\n`;
  const params = new URLSearchParams({
    template: "moderation_report.md",
    title: "Moderation report",
    body,
  });
  return `https://github.com/goodgorithm/goodgorithm/issues/new?${params.toString()}`;
}

export function PostCard({
  post,
  relative,
}: {
  post: FeedPost;
  relative: RelativeFractions;
}) {
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

      <CollapsiblePostText text={post.text} source={post.source} permalink={post.permalink} />
      <EntityTags entities={post.entities} />
      <PostAttachments post={post} />

      <div className={styles.footer}>
        {post.permalink && (
          <div className={styles.links}>
            <a
              className={styles.permalink}
              href={post.permalink}
              target="_blank"
              rel="noreferrer noopener"
            >
              View original ↗
            </a>
            <a
              className={styles.report}
              href={reportUrl(post.permalink)}
              target="_blank"
              rel="noreferrer noopener"
            >
              Report
            </a>
          </div>
        )}
        <ScoreDetails scores={post.scores} relative={relative} />
      </div>
    </article>
  );
}
