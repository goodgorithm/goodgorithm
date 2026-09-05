-- Issue #177: nullable timestamp marking when processing/'s corpus-export
-- sweep last copied a post's text into the long-lived R2 text corpus (the
-- goodgorithm-corpus bucket) used for training the project's own
-- classical-ML embeddings. NULL for posts not yet exported, and for every
-- post while CORPUS_EXPORT_ENABLED is off (staging, local dev). Set
-- exactly once and never re-derived, same contract as moderation_checked_at
-- (0015) and author_resolved_at (0016). Additive/nullable.
ALTER TABLE processed_posts ADD COLUMN exported_at TIMESTAMPTZ;

-- Serves the export sweep's candidate query the same way
-- processed_posts_moderation_pending_idx serves moderation_recheck: it
-- filters and orders on processed_posts alone (source and processed_at
-- both live here) so no raw_posts join is needed to find pending rows.
-- Only dedup-canonical rows are ever exported -- near-duplicate crossposts
-- and syndicated reposts would bias a trained embedding -- so the
-- non-canonical rows stay out of the index.
CREATE INDEX processed_posts_export_pending_idx
  ON processed_posts (processed_at)
  WHERE exported_at IS NULL AND is_dedup_canonical;
