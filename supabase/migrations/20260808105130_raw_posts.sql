CREATE TABLE raw_posts (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  source      TEXT        NOT NULL CHECK (source IN ('bluesky', 'mastodon')),
  source_id   TEXT        NOT NULL,
  author_id   TEXT        NOT NULL,
  text        TEXT        NOT NULL,
  lang        TEXT,
  created_at  TIMESTAMPTZ NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  raw_json    JSONB       NOT NULL,
  UNIQUE (source, source_id)
);

CREATE INDEX raw_posts_created_at_idx  ON raw_posts (created_at DESC);
CREATE INDEX raw_posts_source_idx      ON raw_posts (source);
CREATE INDEX raw_posts_ingested_at_idx ON raw_posts (ingested_at DESC);
