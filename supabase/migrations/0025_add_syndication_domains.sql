-- A moderator-curated list of dedicated RSS->social auto-poster and
-- share-shortener domains (issue #190). A ranked post that links through
-- one carries no original take, so penalties.py's `syndication` entry
-- devalues its base_score -- on either platform, unlike aggregator_instances
-- (Mastodon home instance only). Same table shape + inline RLS as
-- aggregator_instances (0018); a demote, never a hard-delete, so it stays
-- separate from suppressed_domains.
--
-- Additive and off by default (an empty table matches nothing), so it's
-- safe under the sequential ingestion->api->processing deploy -- a
-- processing instance still on old code just never reads it. Seeded only
-- with dedicated auto-posters; general shorteners (bit.ly, buff.ly) are
-- deliberately left off -- people use them by hand too, ~40% false
-- positives in a production sample.
CREATE TABLE syndication_domains (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  domain     TEXT        NOT NULL UNIQUE CHECK (domain = lower(domain)),
  reason     TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE syndication_domains ENABLE ROW LEVEL SECURITY;

INSERT INTO syndication_domains (domain, reason) VALUES
  ('dlvr.it',  'dedicated RSS -> social auto-poster'),
  ('ift.tt',   'IFTTT auto-poster'),
  ('cstu.io',  'ContentStudio marketing scheduler shortener'),
  ('flip.it',  'Flipboard share shortener'),
  ('trib.al',  'SocialFlow / Tribune headline auto-poster');
