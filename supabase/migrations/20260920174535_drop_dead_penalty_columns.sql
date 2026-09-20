-- non-additive: post_shapes.devalue_multiplier and syndication_domains are
-- dead code as of this migration -- penalties.py's registry has no `shape`
-- or `syndication` entry, so neither is read by processing/ anywhere
-- (issue #287). Safe as a single step, not the full add/dual-write/
-- backfill/cut-over/drop sequence CLAUDE.md's Versioning & migration
-- section requires for a reshape: there's no live code path depending on
-- either during the deploy-skew window, since nothing reads them today.
ALTER TABLE post_shapes DROP COLUMN devalue_multiplier;
DROP TABLE syndication_domains;
