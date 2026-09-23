-- processing/ no longer computes sentiment or topicality scores (issue
-- #310), so it stops writing these three columns. Relaxing NOT NULL lets
-- its upserts omit them; this has to be applied before that code deploys,
-- or every processed_posts insert fails. category/category_method were
-- already nullable. Dropping all five columns is a separate, later
-- migration, once no deployed code references them.
ALTER TABLE processed_posts ALTER COLUMN sentiment_score DROP NOT NULL;
ALTER TABLE processed_posts ALTER COLUMN sentiment_method DROP NOT NULL;
ALTER TABLE processed_posts ALTER COLUMN topicality_score DROP NOT NULL;
