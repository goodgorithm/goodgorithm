-- Supabase's advisor flagged blocked_authors, suppressed_terms, and
-- flagged_author_clusters as fully exposed to the anon/authenticated
-- roles via the auto-generated PostgREST API, regardless of whether the
-- app ever calls it -- Supabase exposes every public-schema table by
-- default. No service in this repo uses supabase-js or an anon key
-- (ingestion/api/processing all connect via DATABASE_URL, a direct
-- Postgres role that bypasses RLS), and moderators edit these tables by
-- hand via the Supabase SQL editor (also bypasses RLS) -- so there is no
-- legitimate anon/authenticated consumer to write a policy for. Enabling
-- RLS with zero policies is a complete fix here (default-deny for
-- anon/authenticated), not a partial one waiting on follow-up policies.
ALTER TABLE blocked_authors ENABLE ROW LEVEL SECURITY;
ALTER TABLE suppressed_terms ENABLE ROW LEVEL SECURITY;
ALTER TABLE flagged_author_clusters ENABLE ROW LEVEL SECURITY;
