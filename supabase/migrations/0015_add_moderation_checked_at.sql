-- Issue #67: nullable timestamp marking when processing/'s
-- moderation_recheck.py last independently re-verified a Bluesky post's
-- own moderation labels *and* its author's profile-level self-label
-- against Bluesky's public AppView (app.bsky.feed.getPosts) -- a backstop
-- against ingestion/'s blueskyLabels.ts real-time label-stream listener,
-- which can race Jetstream's own insert for the same post. NULL for
-- Mastodon posts and for Bluesky posts not yet swept. Additive/nullable,
-- same pattern as quote_content (0004) and generated_thumbnail_url (0010).
ALTER TABLE processed_posts ADD COLUMN moderation_checked_at TIMESTAMPTZ;
