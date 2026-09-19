-- Sibling signal for political-content detection (issue #264), same
-- <x>_score/<x>_method pair convention as sentiment_score/sentiment_method
-- and category/category_method. Deliberately not folded into `category` --
-- see CLAUDE.md's Category filtering section for why political content
-- stays out of that 4-category set.
--
-- Additive, nullable, no default: computed by pipeline_stages/political_model.py
-- when a trained classifier is loaded from R2, left NULL otherwise (no
-- keyword-matcher-style fallback for this one). Not yet read by ranking.py,
-- penalties.py, or any exclude check -- observational only.
ALTER TABLE processed_posts ADD COLUMN political_score REAL;
ALTER TABLE processed_posts ADD COLUMN political_method TEXT;
