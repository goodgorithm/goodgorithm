-- Records which mechanism produced a post's category assignment
-- ("tfidf_lr_v1" for the trained classifier, "keyword_v1" for
-- taxonomy.py's fallback when the classifier can't load) -- mirrors
-- sentiment_method's role for sentiment_score. Pure audit metadata: no
-- index (not queried on), not exposed via api/'s FeedPost type (same as
-- sentiment_method), stays processing/DB-internal.
ALTER TABLE processed_posts ADD COLUMN category_method TEXT;
