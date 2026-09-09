-- non-additive: DROP INDEX. Index-only -- a missing index degrades a query
-- to a scan, never errors -- so this is safe to apply in the same push as
-- the code change, and it is recreated under the same name in the next
-- statement. CREATE INDEX (non-concurrent, inside the migration txn) takes
-- a brief SHARE lock on processed_posts; processing/'s next upsert waits a
-- few seconds rather than failing.
--
-- corpus_export.py no longer filters to is_dedup_canonical -- near-duplicate
-- text is kept and the flag is exported per record for a downstream
-- training pipeline to use. Drop is_dedup_canonical from the partial
-- index's predicate so fetch_unexported_posts' widened "exported_at IS
-- NULL" candidate query stays an index scan (already ordered by
-- processed_at, LIMIT stops early) rather than a full processed_posts seq
-- scan + sort every sweep. The pre-change query still uses the widened
-- index during the deploy window: its "exported_at IS NULL AND
-- is_dedup_canonical" predicate implies "exported_at IS NULL".
DROP INDEX IF EXISTS processed_posts_export_pending_idx;
CREATE INDEX processed_posts_export_pending_idx
  ON processed_posts (processed_at)
  WHERE exported_at IS NULL;
