-- Issue #73: resolves a Bluesky post's own author display name/avatar,
-- which Jetstream's firehose never carries (only the DID + record) --
-- unlike Mastodon, whose API response embeds this for free. Mirrors
-- quote_resolver.py's exact resolution shape ({"displayName", "avatarUrl"})
-- for internal consistency, but for the post's own author rather than a
-- quoted one. bluesky_author is NULL for Mastodon rows (which never need
-- it -- api/ reads display name straight from raw_json for those) and for
-- Bluesky rows not yet swept or whose author couldn't be resolved.
-- author_resolved_at mirrors moderation_checked_at's (0015) "swept once,
-- never forever" role -- distinguishes "not yet attempted" from "attempted,
-- no author data available" so a permanently-unresolvable post isn't
-- retried every sweep. Additive/nullable, same pattern as quote_content
-- (0004), generated_thumbnail_url (0010), and moderation_checked_at (0015).
ALTER TABLE processed_posts ADD COLUMN bluesky_author JSONB;
ALTER TABLE processed_posts ADD COLUMN author_resolved_at TIMESTAMPTZ;
