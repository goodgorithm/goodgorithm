-- Issue #43: a generated fallback thumbnail (processing/'s own og:image
-- fetch, processing/src/thumbnail_resolver.py) for link posts whose
-- source platform didn't capture one. Nullable/additive, same pattern as
-- quote_content -- computed once at scoring time, read straight through
-- by api/, never re-derived.
ALTER TABLE processed_posts ADD COLUMN generated_thumbnail_url TEXT;
