-- Sibling signal for the #238 epic's quality classifier ("would a human
-- call this good" -- positivity and substance together), same <x>_score/
-- <x>_method pair convention as sentiment_score/political_score. Additive,
-- nullable, no default: computed by pipeline_stages/quality_model.py when
-- a trained classifier is loaded from R2, left NULL otherwise (no
-- fallback for this one, same as political_score). Unlike political_score,
-- every persisted row already cleared quality_exclude.py's threshold --
-- posts scoring below it are deleted before ever reaching this table.
ALTER TABLE processed_posts ADD COLUMN quality_score REAL;
ALTER TABLE processed_posts ADD COLUMN quality_method TEXT;
