-- Candidate coordinated-bot-network clusters (issue #44), for moderator
-- review only -- never auto-acted on, same "human-decided" precedent as
-- blocked_authors (issue #7). A moderator reviews via the Supabase SQL
-- editor (no admin UI, same as blocked_authors) and either copies
-- author_ids into blocked_authors or marks dismissed_at on a false
-- positive.
--
-- home_domain UNIQUE + the upsert in processing/src/db.py's
-- upsert_flagged_clusters means re-running the detector refreshes an
-- existing candidate's counts rather than creating duplicate rows for
-- the same domain.
CREATE TABLE flagged_author_clusters (
  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  home_domain                  TEXT NOT NULL UNIQUE,
  author_ids                   TEXT[] NOT NULL,
  account_count                INT NOT NULL,
  post_count                   INT NOT NULL,
  earliest_account_created_at  TIMESTAMPTZ NOT NULL,
  latest_account_created_at    TIMESTAMPTZ NOT NULL,
  detected_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  dismissed_at                 TIMESTAMPTZ
);
