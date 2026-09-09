-- Consolidate the base_score devalue penalties into one abstraction
-- (issue #199). pipeline_stages/penalties.py is now a single registry that
-- runs every penalty (context-dependency, bare link-share, aggregator
-- instance, post shape, ...) and returns their product.
--
--   penalty_multiplier  -- the product; compute_base_score / refresh_rankings
--                          read only this
--   penalty_detail      -- JSONB per-penalty breakdown
--                          ({"context": 0.4, "link_share": 1.0, ...,
--                           "shape_name": "nowplaying"}), the audit surface
--
-- Additive: DEFAULT 1.0 / NULL so the pre-#199 code is unaffected, and the
-- new code dual-writes the individual context_penalty / link_share_penalty /
-- aggregator_penalty / shape_penalty / shape_name columns from the same
-- values until a follow-up migration drops them (the nowplaying_penalty
-- pattern). Same DEFAULT-1.0 safety as add_link_share_penalty /
-- add_aggregator_demotion / add_post_shapes.
ALTER TABLE processed_posts ADD COLUMN penalty_multiplier REAL DEFAULT 1.0;
ALTER TABLE processed_posts ADD COLUMN penalty_detail JSONB;
