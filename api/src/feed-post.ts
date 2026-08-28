import { buildAttachments } from "./attachments";
import { buildAuthor } from "./author";
import type { FeedRow } from "./db";
import { buildEmojis } from "./emoji";
import { buildPermalink } from "./permalink";
import type { FeedPost } from "./types";

// The DB row -> public FeedPost shaping, factored out of routes/feed.ts's
// handler so it's callable in isolation (mirrors buildAttachments/buildAuthor/
// buildEmojis/buildPermalink, which are already their own testable units).
// The `: FeedPost` return annotation is load-bearing: it's the one place the
// row -> wire-shape boundary is type-checked. See tests/android-contract.test.ts.
export function rowToFeedPost(row: FeedRow): FeedPost {
  const { attachments, sensitive } = buildAttachments(row);
  return {
    id: row.id,
    source: row.source,
    author_id: row.author_id,
    text: row.text,
    // FeedRow.created_at is a Date (postgres.js maps timestamptz that way);
    // the wire shape is an ISO string. Serialize explicitly here rather than
    // leaning on Fastify's JSON step, so the return type is honest.
    created_at: row.created_at.toISOString(),
    entities: row.entities ?? [],
    permalink: buildPermalink(row),
    author: buildAuthor(row),
    emojis: buildEmojis(row.mastodon_status_emojis),
    scores: {
      sentiment: row.sentiment_score,
      topicality: row.topicality_score,
      base: row.base_score,
      rank: row.rank_score,
    },
    pipeline_version: row.pipeline_version,
    attachments,
    sensitive,
    // FeedRow.category is `string | null` on purpose: processing/ can write a
    // category value api/ doesn't know yet, and it passes straight through
    // (see CLAUDE.md's Category taxonomy note). The cast keeps that.
    category: row.category as FeedPost["category"],
  };
}
