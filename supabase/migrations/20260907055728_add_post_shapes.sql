-- Post-shape registry knobs (issue #196, generalizing #189's now-playing
-- detector). The regex patterns and key-extraction logic live in
-- processing/src/pipeline_stages/post_shape.py's code registry -- processing/
-- is one long-lived loop with no regex timeout, so a DB-sourced pattern
-- would be an unmitigated ReDoS surface. This table carries only the
-- operational knobs a moderator can turn without a deploy: enable/disable a
-- shape, and tune its base_score devalue multiplier and bot-filter repeat
-- threshold. A shape with no row here falls back to its code-registry
-- literals. Same "curate the data live, keep the mechanism in code" split as
-- aggregator_instances. RLS inline, matching add_suppressed_domains /
-- add_aggregator_demotion.
CREATE TABLE post_shapes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE CHECK (name = lower(name)),
  enabled BOOLEAN NOT NULL DEFAULT true,
  devalue_multiplier REAL NOT NULL DEFAULT 1.0 CHECK (devalue_multiplier > 0 AND devalue_multiplier <= 1),
  -- NULL -> this shape never feeds the bot filter's is_bot override (devalue only).
  repeat_threshold INTEGER CHECK (repeat_threshold >= 1),
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE post_shapes ENABLE ROW LEVEL SECURITY;

INSERT INTO post_shapes (name, devalue_multiplier, repeat_threshold, reason) VALUES
  ('nowplaying', 0.3, 3, 'radio / stream "now playing on <station>" bots (issue #189)');

-- Renames processed_posts.nowplaying_penalty -> shape_penalty (the generic
-- post-shape devalue multiplier) and adds shape_name (which shape fired).
-- Additive: the new code dual-writes nowplaying_penalty = shape_penalty
-- until the drop_nowplaying_penalty migration drops the old column, so a
-- processing instance still on v9 during the sequential deploy keeps reading
-- a correct value. Same DEFAULT-1.0 safety as add_link_share_penalty /
-- add_nowplaying_penalty.
ALTER TABLE processed_posts ADD COLUMN shape_penalty REAL DEFAULT 1.0;
ALTER TABLE processed_posts ADD COLUMN shape_name TEXT;
