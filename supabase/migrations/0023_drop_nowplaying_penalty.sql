-- Second step of the processed_posts.nowplaying_penalty -> shape_penalty
-- rename (issue #196). 0022 added shape_penalty/shape_name and the v10 code
-- dual-wrote nowplaying_penalty = shape_penalty; v11 stops writing it and
-- nothing reads it (refresh_rankings switched to shape_penalty in 0022's
-- code). Non-additive, so this is deliberately its own migration + deploy:
-- apply it only once the v11 deploy is confirmed live in the target
-- environment, so no still-running v10 process tries to write a column that
-- no longer exists. 24h retention has long since aged out every pre-0022
-- (v9) row, so there is no historical data on the column to preserve.
ALTER TABLE processed_posts DROP COLUMN nowplaying_penalty;
