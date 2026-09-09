-- Manual moderation blocklist (issue #7). Checked at processing time,
-- same "hard exclude before ever scored/shown" pattern as
-- content_filter.py's hashtag/self-label checks. Moderators (today: by
-- hand, e.g. via the Supabase SQL editor) add a (source, author_id) row
-- once a bad actor is identified; every future post from that author is
-- excluded before dedup/bot/topicality ever run, and any already-ingested
-- posts get purged within one processing cycle (processing/src/db.py's
-- purge_blocked_authors). Also written to automatically by
-- ingestion/src/blueskyLabels.ts when Bluesky's own moderation service
-- applies its official "bot" account label -- same sink for both a human
-- moderator's decision and this one automated signal.
CREATE TABLE blocked_authors (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  source     TEXT        NOT NULL CHECK (source IN ('bluesky', 'mastodon')),
  author_id  TEXT        NOT NULL,
  reason     TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (source, author_id)
);

-- Supports both the per-post exclusion check and the retroactive purge
-- query -- raw_posts had no existing index on author_id.
CREATE INDEX raw_posts_source_author_idx ON raw_posts (source, author_id);
