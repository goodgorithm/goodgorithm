-- "Now playing on <station>" radio/stream ranking devaluation (issue #189).
-- Additive, nullable-with-default, same shape as 0017_add_link_share_penalty.sql
-- and 0018_add_aggregator_demotion.sql's penalty column: safe under the
-- sequential ingestion->api->processing deploy -- a processing instance still
-- on old code just never writes it, and DEFAULT 1.0 leaves base_score maths
-- unchanged for those rows.
ALTER TABLE processed_posts ADD COLUMN nowplaying_penalty REAL DEFAULT 1.0;
