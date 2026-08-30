-- Aggregator-instance ranking demotion (issue #141). Two additive changes:
--
-- 1. aggregator_instances: a hand-curated list of Mastodon home instances whose
--    content is automated syndication (curated headline/link reposts) rather than
--    original posts -- Flipboard's federating "magazine" accounts alone were ~34%
--    of ranked Mastodon feed content. NOT an exclusion (Flipboard isn't
--    off-mission) -- a separate table from suppressed_domains precisely because
--    adding a domain there hard-deletes the post; a row here only devalues
--    base_score (aggregator_demote.py). Same "moderator edits rows directly via
--    the Supabase SQL editor, no deploy" precedent as blocked_authors /
--    suppressed_terms / suppressed_domains. RLS enabled inline, same as
--    suppressed_domains (0014).
--
-- 2. processed_posts.aggregator_penalty: aggregator_demote.py's per-post devalue
--    multiplier, same pattern as context_penalty (0008) / link_share_penalty
--    (0017) -- computed once at scoring time, read back on every refresh_rankings
--    MMR pass. DEFAULT 1.0 leaves base_score maths unchanged for existing rows and
--    any post whose home instance isn't listed, so it's safe under the sequential
--    ingestion->api->processing deploy: a processing instance still on old code
--    just never writes it.
CREATE TABLE aggregator_instances (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  domain     TEXT        NOT NULL UNIQUE CHECK (domain = lower(domain)),
  reason     TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE aggregator_instances ENABLE ROW LEVEL SECURITY;

INSERT INTO aggregator_instances (domain, reason) VALUES
  ('flipboard.com', 'automated magazine aggregator, ~34% of ranked Mastodon content -- issue #141'),
  ('flipboard.social', 'automated magazine aggregator -- issue #141');

ALTER TABLE processed_posts ADD COLUMN aggregator_penalty REAL DEFAULT 1.0;
