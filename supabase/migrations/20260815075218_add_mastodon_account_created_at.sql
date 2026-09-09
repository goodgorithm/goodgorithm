-- Promotes Mastodon's account.created_at out of raw_json into a real
-- column (issue #44) -- network_detector.py's coordinated-bot-network
-- clustering needs this for every Mastodon row, and a
-- raw_json->'account'->>'created_at' JSON-path extraction across the
-- full ~220k-row Mastodon population timed out (same class of problem
-- CLAUDE.md already documents for a similar content ilike scan). Same
-- pattern as text/lang/author_id: a frequently-queried field promoted
-- out of raw_json into a real, indexable column rather than paying JSON
-- parse cost on every query. NULL for Bluesky rows (no equivalent
-- concept) and for any Mastodon row ingested before this column existed.
ALTER TABLE raw_posts ADD COLUMN mastodon_account_created_at TIMESTAMPTZ;

-- Supports fetch_cluster_candidates' filter/aggregate without touching
-- raw_json at all.
CREATE INDEX raw_posts_mastodon_account_created_idx
  ON raw_posts (source, mastodon_account_created_at)
  WHERE source = 'mastodon';
