-- DB-backed replacement for content_filter.py's old hardcoded
-- EXCLUDED_HASHTAGS frozenset (issue #39) -- a Mastodon spam/adult-content
-- post reached the feed because none of its hashtags (#CamGirls, #Pussy,
-- #OnlyFans, #Domination, #Fetish) matched the old frozenset({"nsfw"}).
-- Same "moderator adds/removes rows directly, no code change or service
-- restart needed" precedent as blocked_authors (issue #7, migration 0006):
-- today, by hand, via the Supabase SQL editor -- no admin UI/CLI,
-- deliberately, same as that table.
--
-- Named suppressed_terms, not excluded_hashtags -- it also matches against
-- Mastodon's free-text spoiler_text content-warning field
-- (content_filter.py's has_excluded_spoiler_text), not just #hashtags in
-- the post body -- both are the same deliberate self-tagging signal.
--
-- Deliberately narrow and hand-curated -- precision over recall (Decisions
-- Log, 2026-08-11), same standard as the code comment this table replaces:
-- only terms that function as an unambiguous self-tagging convention for
-- adult content, not identity/topic terms that merely correlate with it in
-- some posts (e.g. NOT "lesbian" -- an identity term; hard-excluding it
-- would flag ordinary LGBTQ+ content as adult, a discrimination risk, not
-- a precision win). CHECK enforces lowercase storage since matching is
-- always done lowercased.
CREATE TABLE suppressed_terms (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  term       TEXT        NOT NULL UNIQUE CHECK (term = lower(term)),
  reason     TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO suppressed_terms (term, reason) VALUES
  ('nsfw', 'carried over from content_filter.py''s original EXCLUDED_HASHTAGS'),
  ('pussy', 'issue #39 -- unambiguous adult self-tag'),
  ('camgirls', 'issue #39 -- unambiguous adult self-tag'),
  ('onlyfans', 'issue #39 -- unambiguous adult self-tag'),
  ('domination', 'issue #39 -- unambiguous adult self-tag'),
  ('fetish', 'issue #39 -- unambiguous adult self-tag');
-- Deliberately NOT seeded, same precision-over-recall reasoning: glamour,
-- highclass, love -- ambiguous outside context, not an unambiguous
-- adult-content self-tagging convention (issue #39's reported post also
-- carried these, but they don't clear the same bar as the terms above).
