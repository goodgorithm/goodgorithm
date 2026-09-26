# Training data export runbook

Procedure for exporting reviewed posts from the `labeling` schema into a file a training
notebook can consume. **What** the `labeling` schema is and **why** it's shaped the way it
is lives in [`CLAUDE.md`'s Architecture section](../CLAUDE.md#architecture-as-built) (the
`labeling/` row) and the `labeling.posts`/`labeling.labels` migration's own header comment —
this file is just the how-to.

## Find the study

Every export is scoped to one `labeling.studies` row (a slug + a taxonomy). List them to find
the right `study_id`:

```sql
SELECT id, slug, name FROM labeling.studies;
```

## The export query

```sql
SELECT
  p.id,
  p.source,
  p.text,
  p.hashtags,
  p.attachments,
  p.quote_content,
  p.context_kind,
  p.original_created_at,
  p.rank_score,
  p.batch,
  ml.category,
  ml.taxonomy_flag
FROM labeling.posts p
JOIN LATERAL (
  SELECT category, taxonomy_flag
  FROM labeling.labels
  WHERE post_id = p.id AND reviewer = 'maintainer'
  ORDER BY created_at DESC
  LIMIT 1
) ml ON true
WHERE p.study_id = '<study_id>'
ORDER BY p.original_created_at;
```

`labeling.labels` is insert-only — a post can carry more than one `reviewer = 'maintainer'`
row if a maintainer corrected an earlier label. The `JOIN LATERAL ... ORDER BY created_at DESC
LIMIT 1` picks the latest one per post, so this query returns exactly one row per reviewed
post. This mirrors `labeling/src/db.ts`'s own `exportLabelled()` function (the labelling
service's built-in CSV export) — don't drop the `LATERAL`/`LIMIT 1` in favor of a plain
`JOIN ... WHERE reviewer = 'maintainer'`, which would emit one row per label instead of one
row per post whenever a correction exists.

Only posts with at least one `reviewer = 'maintainer'` label are returned — an AI-drafted
label alone (`reviewer = 'ai'`) doesn't count as reviewed and is excluded.

Before exporting, it's worth a quick duplicate-content check — the candidate-collection step
has no de-dup against already-collected posts, so the same underlying post can end up as more
than one `labeling.posts` row (different `id`, identical `text`), usually from two collection
passes run close together:

```sql
SELECT text, COUNT(*) AS n, array_agg(id) AS ids
FROM labeling.posts
WHERE study_id = '<study_id>'
GROUP BY text
HAVING COUNT(*) > 1;
```

If this returns rows, check whether the duplicates' labels agree before deciding what to do —
if they agree (the common case), it's safe to keep the earliest-inserted row and delete the
rest (`labeling.labels` first, then `labeling.posts`, to satisfy the foreign key); if they
disagree, that's a real labeling inconsistency worth a human look before resolving either way.

## Running it and publishing the result

Run via the Supabase MCP (`execute_sql`, production project) or the Supabase SQL editor —
same as every other one-off query against this project's data. Save the result as a JSON
array (the SQL editor's "export as JSON" works directly; via the MCP, extract the returned
rows into a `.json` file). The resulting shape is what `training/quality_classifier.ipynb`
(and any future training notebook) expects: one object per post with at least `id`, `text`,
and `category` — the other columns above are carried through for context but not required by
every consumer.

**Commit the result to `training/data/feed-quality-labels.json`** (named after the
`feed-quality-pilot` study slug) rather than leaving it as a local, uncommitted file —
`research/` is gitignored (scratch/one-off analysis only, see its own note in `.gitignore`),
so a dataset that only ever lives there isn't actually published anywhere durable. Committing
the export gives every future retrain a real, diffable history of how the labelled set grew
between versions, and makes it a real input to `training/quality_classifier.ipynb` — either
uploaded fresh each run (the notebook's default) or read directly if running with local repo
access.

This is a manual, repeat-when-retraining step, not an automated script — consistent with
`doc/MODERATION.md`'s "no admin UI, done by hand" precedent for this project's other
one-off data operations.
