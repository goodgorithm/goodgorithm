-- non-additive: DROP COLUMN. Apply only once the v14 deploy that stopped
-- writing these columns is confirmed live in the target environment, so no
-- still-running v13 process tries to write a column that no longer exists.
--
-- Final step of the base_score penalty consolidation (issue #199). The
-- add_penalty_box_columns migration added penalty_multiplier (the product,
-- read by ranking) and penalty_detail (the per-penalty JSONB breakdown); the
-- v12/v13 code dual-wrote the individual columns from the same values. v14
-- stops writing them and nothing reads them (fetch_rankable_posts switched
-- to penalty_multiplier). Retention (24h) long since aged out every
-- pre-consolidation row, and the columns have held nothing but a copy of
-- penalty_detail's entries since.
ALTER TABLE processed_posts
  DROP COLUMN context_penalty,
  DROP COLUMN link_share_penalty,
  DROP COLUMN aggregator_penalty,
  DROP COLUMN shape_penalty,
  DROP COLUMN shape_name;
