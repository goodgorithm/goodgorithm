CREATE TABLE processed_posts (
  id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  raw_post_id          UUID        NOT NULL UNIQUE REFERENCES raw_posts(id),
  dedup_cluster_id     UUID        NOT NULL,
  is_dedup_canonical   BOOLEAN     NOT NULL DEFAULT true,
  is_bot               BOOLEAN     NOT NULL DEFAULT false,
  bot_score            REAL,
  sentiment_score      REAL        NOT NULL,
  sentiment_method     TEXT        NOT NULL,
  topicality_score     REAL        NOT NULL,
  entities             JSONB,
  base_score           REAL,
  rank_score           REAL,
  pipeline_version     TEXT        NOT NULL DEFAULT 'v1',
  processed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX processed_posts_dedup_cluster_idx ON processed_posts (dedup_cluster_id);
CREATE INDEX processed_posts_eligible_idx      ON processed_posts (is_bot, is_dedup_canonical);
CREATE INDEX processed_posts_rank_score_idx    ON processed_posts (rank_score DESC);
