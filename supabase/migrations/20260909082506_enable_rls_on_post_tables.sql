-- Supabase auto-enables row-level security on every table in the public
-- schema; raw_posts / processed_posts predate the moderation-table
-- migrations that started doing it explicitly (add_blocked_authors,
-- enable_rls_on_moderation_tables, add_suppressed_domains, ...), so the
-- migration files don't record it. On the production project and the
-- staging branch it's already on -- this is a no-op there -- but a fresh
-- `supabase db reset` or a new preview branch built from these files alone
-- would bring both tables up with RLS off.
--
-- There are no RLS policies on either table (nothing in the public schema
-- has any), and no Data-API access to them: ingestion/, processing/, and
-- api/ all connect with a role that bypasses RLS. This purely closes the
-- drift so `supabase/migrations/` fully describes the live schema.
ALTER TABLE raw_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE processed_posts ENABLE ROW LEVEL SECURITY;
