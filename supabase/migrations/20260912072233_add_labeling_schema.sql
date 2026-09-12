-- Storage for the labeling/ service (issue #245) -- the human-review tool
-- for research-effort evaluation sets (#233's political/civic tone, #240's
-- feed-quality substance, and future ones), replacing the previous
-- self-publishing Claude Artifact. A dedicated schema keeps this
-- organizationally separate from the core pipeline's raw_posts/
-- processed_posts while living in the same Postgres instance -- no new
-- database technology, no new migration convention.
--
-- One study per research effort (its taxonomy + which dataset it's
-- labelling); posts are review candidates; labels are one row per labelling
-- *event* rather than columns on posts, so an AI-drafted suggestion and a
-- maintainer's confirmation/correction are both just rows distinguished by
-- `reviewer`, and every correction is preserved (insert-only) instead of
-- overwritten -- the table doubles as its own audit trail.

CREATE SCHEMA IF NOT EXISTS labeling;

CREATE TABLE labeling.studies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    categories JSONB NOT NULL, -- [{id, label, color}, ...] -- what the old tool hardcoded into HTML/JS
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE labeling.posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id UUID NOT NULL REFERENCES labeling.studies(id),
    source TEXT,
    rank_score DOUBLE PRECISION,
    original_created_at TIMESTAMPTZ,
    text TEXT NOT NULL,
    hashtags TEXT[] NOT NULL DEFAULT '{}', -- hashtag_bag.py/content_filter.py/taxonomy.py all act on these
    attachments JSONB, -- link cards / images / video -- same shape as api/src/attachments.ts's
                        -- Attachment[], captured at candidate-creation time since raw_posts.raw_json
                        -- is gone after 24h retention by the time labelling happens
    quote_content JSONB, -- same shape as processed_posts.quote_content (quote_resolver.py)
    batch TEXT, -- which import/snapshot a candidate came from
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON labeling.posts (study_id, batch);

CREATE TABLE labeling.labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES labeling.posts(id),
    reviewer TEXT NOT NULL, -- 'ai' or 'maintainer' for now; free text, not an enum, so a real
                             -- per-person reviewer identity is additive later, not a rewrite
    category TEXT NOT NULL,
    taxonomy_flag BOOLEAN NOT NULL DEFAULT false,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON labeling.labels (post_id, created_at DESC);

-- Matches the enable_rls_on_post_tables migration's fix for raw_posts/
-- processed_posts: no RLS policies needed (labeling/ connects with a role
-- that bypasses RLS, same as every other service; there's no Data-API
-- access to this schema), but explicit is better than relying on whatever
-- a fresh project's default happens to be.
ALTER TABLE labeling.studies ENABLE ROW LEVEL SECURITY;
ALTER TABLE labeling.posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE labeling.labels ENABLE ROW LEVEL SECURITY;
