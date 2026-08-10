-- Holds the pre-shaped, already-content-filtered quote-post content
-- resolved by processing/'s quote_resolver.py at scoring time (author,
-- text, createdAt, or an unavailable/filtered status) -- api/ passes this
-- straight through, no further shaping. NULL for Mastodon posts, posts
-- with no quote embed, and posts scored before this column existed.
ALTER TABLE processed_posts ADD COLUMN quote_content JSONB;
