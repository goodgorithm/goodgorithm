-- Persists context_dependency.py's per-post devalue multiplier (issue #33)
-- as a base_score component, same pattern as sentiment_score/
-- topicality_score: computed once at processing time, read back on every
-- refresh_rankings() MMR pass rather than re-parsing raw_json each cycle
-- (which would mean re-fetching the full raw_json blob for every post in
-- the rankable window, every 30s -- a real cost at production's 5k-30k+
-- eligible-window scale, see ranking.py's MMR_CANDIDATE_POOL_SIZE
-- comments). Defaults to 1.0 (no penalty) for existing rows and any post
-- a platform's policy doesn't flag.
ALTER TABLE processed_posts ADD COLUMN context_penalty REAL DEFAULT 1.0;
