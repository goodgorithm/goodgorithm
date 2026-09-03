-- Issue #173: author_resolver.py and moderation_recheck.py select their
-- pending work from processed_posts alone. source is denormalized from
-- raw_posts (immutable after ingestion) so their candidate queries need
-- no raw_posts join to decide which rows are pending, and no raw_posts
-- column in their ORDER BY -- a partial index on processed_posts serves
-- the whole query. Filtering r.source or ordering by raw_posts.created_at
-- instead drives the plan off raw_posts_created_at_idx and scans the
-- entire Bluesky raw_posts set on every sweep whenever the pending set is
-- smaller than the batch size, which is the normal caught-up state.
-- Additive/nullable column, same pattern as the other processed_posts
-- columns.
ALTER TABLE processed_posts ADD COLUMN source TEXT;

UPDATE processed_posts p
SET source = r.source
FROM raw_posts r
WHERE r.id = p.raw_post_id AND p.source IS NULL;

-- The two resolver work-sets. In the caught-up steady state each holds
-- only the small rolling set of just-scored Bluesky posts a sweep hasn't
-- reached yet; during a backlog each is bounded by the 24h retention
-- window, and the sweep drains it in processed_at order LIMIT n per run
-- rather than rescanning raw_posts. Both resolvers are Bluesky-only, so
-- the source = 'bluesky' predicate keeps the indexes small.
CREATE INDEX processed_posts_moderation_pending_idx
  ON processed_posts (processed_at DESC)
  WHERE source = 'bluesky' AND moderation_checked_at IS NULL;

CREATE INDEX processed_posts_author_pending_idx
  ON processed_posts (processed_at DESC)
  WHERE source = 'bluesky' AND rank_score IS NOT NULL AND author_resolved_at IS NULL;
