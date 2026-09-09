-- Issue #211: existence_recheck.py sweeps already-ranked Bluesky posts and
-- deletes the raw_posts row (processed_posts cascades) once the source post
-- stops resolving on Bluesky's AppView -- covering user deletes, post
-- detach, and account takedowns, none of which emit a com.atproto.label
-- event the label stream or moderation_recheck.py could catch.
--
-- Unlike moderation_checked_at / author_resolved_at (set exactly once),
-- this column is re-derived: it records the last time the post was
-- confirmed present, and the sweep re-checks a row once it is older than
-- EXISTENCE_RECHECK_STALE_HOURS, over the post's whole 24h feed life. A
-- takedown typically lands hours after ingestion, well past a one-shot
-- check.
--
-- Additive/nullable column, same pattern as the other processed_posts
-- resolver columns. The partial index mirrors
-- processed_posts_author_pending_idx but is ordered by
-- existence_checked_at ASC NULLS FIRST so the candidate query --
-- "never checked, or checked longer ago than the stale window" -- is a
-- forward range scan that stops at LIMIT.
ALTER TABLE processed_posts ADD COLUMN existence_checked_at timestamptz;

CREATE INDEX processed_posts_existence_pending_idx
  ON processed_posts (existence_checked_at ASC NULLS FIRST)
  WHERE source = 'bluesky' AND rank_score IS NOT NULL;
