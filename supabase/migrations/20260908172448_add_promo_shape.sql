-- Operational knobs for the `promo` post-shape (issue #191). The regexes
-- and per-group key extraction live in
-- processing/src/pipeline_stages/post_shape.py's code registry -- processing/
-- is one long-lived loop with no regex timeout, so a DB-sourced pattern
-- would be an unmitigated ReDoS surface. This row only carries the
-- deploy-free tunables (enable/disable, base_score devalue multiplier,
-- bot-filter repeat threshold), overriding the registry literals. Same
-- shape as the add_post_shapes `nowplaying` seed; a shape with no row falls back to its
-- code literals. Live-tune with `UPDATE post_shapes SET ... WHERE
-- name = 'promo'` -- effect within MODERATION_LISTS_REFRESH_SECONDS.
INSERT INTO post_shapes (name, enabled, devalue_multiplier, repeat_threshold, reason) VALUES
  ('promo', true, 0.35, 6,
   'marketing / promo phrase patterns: content-farm reposts, directory-submission CTAs, affiliate / referral, asset-store listings, SEO listicles, B2B pitch (issue #191)');
