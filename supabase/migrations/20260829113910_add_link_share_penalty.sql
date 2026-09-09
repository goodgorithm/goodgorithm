-- Bare link-share ranking devaluation (issue #130). Additive, nullable-with-default,
-- same shape as 0008_add_context_penalty.sql: safe under the sequential
-- ingestion->api->processing deploy -- a processing instance still on old code just
-- never writes it, and DEFAULT 1.0 leaves base_score maths unchanged for those rows.
ALTER TABLE processed_posts ADD COLUMN link_share_penalty REAL DEFAULT 1.0;
