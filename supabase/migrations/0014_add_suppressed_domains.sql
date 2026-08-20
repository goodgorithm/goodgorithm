-- DB-backed marketing/affiliate-content blocklist (issue #57 workstream C)
-- -- production sampling found marketing content passing content_filter.py's
-- existing checks by scoring well on sentiment (enthusiastic marketing
-- adjectives), not by evading any hashtag/self-label/spoiler-text signal --
-- a different exclusion mechanism was needed, not a suppressed_terms entry.
-- Same "moderator adds/removes rows directly, no code change or service
-- restart needed" precedent as blocked_authors (migration 0006) and
-- suppressed_terms (migration 0009): today, by hand, via the Supabase SQL
-- editor -- no admin UI/CLI, deliberately, same as those two tables.
--
-- Domain-based, not URL-based -- matches content_filter.py's
-- has_excluded_domain, which checks a post's extracted link's netloc
-- (exact match or subdomain of a listed domain), not the full URL.
--
-- Seeded narrow and hand-curated, same "precision over recall" standard as
-- suppressed_terms (migration 0009): a 20-post hand sample of amazon.com/
-- etsy.com/amzn.to-linked posts from real production data was 20/20
-- genuine marketing/affiliate content with zero false positives, and the
-- two domains account for the large majority of marketing-content volume
-- found (796 posts vs. 55 combined across 12 other marketplace/press-
-- release domains checked) -- see issue #57 for the full research. RLS is
-- enabled in this same migration (unlike blocked_authors/suppressed_terms,
-- which needed a follow-up migration 0013 to add it) -- no reason to
-- repeat that gap for a brand-new table.
CREATE TABLE suppressed_domains (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  domain     TEXT        NOT NULL UNIQUE CHECK (domain = lower(domain)),
  reason     TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE suppressed_domains ENABLE ROW LEVEL SECURITY;

INSERT INTO suppressed_domains (domain, reason) VALUES
  ('amazon.com', 'marketing/affiliate content -- issue #57'),
  ('amzn.to', 'marketing/affiliate content -- issue #57'),
  ('etsy.com', 'marketing/affiliate content -- issue #57');
