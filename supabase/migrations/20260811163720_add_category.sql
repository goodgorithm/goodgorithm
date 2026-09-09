-- Assigned by processing/'s taxonomy.py at scoring time from entity types +
-- top TF-IDF terms via a hand-curated lookup table (classical rule-based
-- matching, no LLM/trained classifier -- CLAUDE.md's no-LLM-in-the-algorithm
-- constraint). NULL when nothing matched -- those posts stay visible only in
-- the unfiltered feed, not any category view. One of a fixed 8-value set.
ALTER TABLE processed_posts ADD COLUMN category TEXT;

CREATE INDEX processed_posts_category_rank_idx
  ON processed_posts (category, rank_score DESC, id DESC);
