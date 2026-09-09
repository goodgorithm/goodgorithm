-- Data-only, no schema change. ingestion/'s Jetstream kind:"account"
-- handler drops a taken-down / suspended / deleted Bluesky account's
-- raw_posts directly (bluesky.ts's deleteByAuthor), so it no longer
-- writes a blocked_authors row per account takedown. Clear the rows that
-- path already accreted: a taken-down account emits nothing more, and its
-- posts are already gone, so these rows only bloat ingestion/'s
-- getBlockedAuthors cache and processing/'s purge_blocked_authors join.
-- Idempotent -- a replay after the code change deletes 0.
DELETE FROM blocked_authors WHERE reason LIKE 'jetstream account %';
