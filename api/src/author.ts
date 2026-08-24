import { buildEmojis } from "./emoji";
import type { FeedPostAuthor } from "./types";

export interface AuthorSource {
  mastodon_display_name: string | null;
  mastodon_avatar_url: string | null;
  bluesky_author_display_name: string | null;
  bluesky_author_avatar_url: string | null;
  mastodon_account_emojis: unknown;
}

// Mastodon's raw_json carries the author's display name/avatar for free.
// Bluesky's Jetstream firehose doesn't - bluesky_author_* is only populated
// once author_resolver.py's sweep resolves it via Bluesky's AppView, and
// only for already-ranked posts, so it stays null until then (or forever,
// for an unresolvable author). Exactly one side is ever non-null per row,
// by source.
export function buildAuthor(row: AuthorSource): FeedPostAuthor {
  return {
    display_name: row.mastodon_display_name ?? row.bluesky_author_display_name,
    avatar_url: row.mastodon_avatar_url ?? row.bluesky_author_avatar_url,
    emojis: buildEmojis(row.mastodon_account_emojis),
  };
}
