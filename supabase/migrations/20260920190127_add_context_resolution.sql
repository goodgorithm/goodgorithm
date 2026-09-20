-- Issue #292: resolved reply/quote-parent context. context_status tracks
-- the sweep state per post -- NULL (not context-dependent), 'pending'
-- (awaiting resolution), 'resolved' (context resolved, quality_score
-- reflects min(own, parent)), 'unavailable' (resolution failed or the
-- parent didn't clear content/language/political filtering -- scored
-- standalone on the post's own text). context_kind distinguishes 'quote'
-- vs 'reply' for display copy. context_content mirrors quote_content's
-- shape ({status: "available", author, text, createdAt} | {status:
-- "unavailable", reason}), generalized to cover both kinds -- quote_content
-- itself stays as-is; processing/ stops writing new values to it once this
-- covers the same case, and dropping it is separate later cleanup.
ALTER TABLE processed_posts ADD COLUMN context_status TEXT;
ALTER TABLE processed_posts ADD COLUMN context_kind TEXT;
ALTER TABLE processed_posts ADD COLUMN context_content JSONB;

-- Same reasoning as processed_posts_moderation_pending_idx /
-- processed_posts_author_pending_idx: filters/orders on processed_posts
-- alone via the already-denormalized `source` column, so the sweep query
-- never touches raw_posts to decide its work-set.
CREATE INDEX processed_posts_context_pending_idx
  ON processed_posts (processed_at DESC)
  WHERE context_status = 'pending';
