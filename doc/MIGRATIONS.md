# Database migrations runbook

Procedure for changing the Postgres schema. **Why** the schema is shaped the way it is lives
in the migration files' own header comments and [`CLAUDE.md`'s Versioning & migration
section](../CLAUDE.md#versioning--migration) — this file is just the how-to.

## Where things live

- `supabase/migrations/*.sql` — the migrations, named `<14-digit-UTC-timestamp>_<lower_snake_slug>.sql`.
- `supabase_migrations.schema_migrations` (in each Supabase project) — the applied-history
  table. `version` = the 14-digit timestamp from the filename.
- Two Supabase projects: **production** (the default branch) and a persistent **staging**
  branch. Each has its own `schema_migrations`.

## Adding a migration

```
supabase migration new <slug>          # writes supabase/migrations/<timestamp>_<slug>.sql
```

Write the DDL. Keep it **additive** — nullable or defaulted columns, new tables, new
indexes. No `DROP`, no `RENAME`, no `ALTER COLUMN … TYPE`, no `TRUNCATE` (see "Non-additive"
below). Add a header comment saying what the change is for; reference other migrations by
their **slug** (`the add_post_shapes migration`), not a number — numbers aren't in the
filenames.

Commit the migration in the **same PR** as the code that needs it, as every existing
migration was.

## How it gets applied

- **Local dev**: `supabase start` applies everything in `supabase/migrations/` automatically.
- **CI, on every push + PR**: `scripts/check-migrations.mjs` (the `migration-checks` job)
  validates filenames, strictly-increasing timestamps, and the additive-only rule.
- **CI, on push to `staging` / `production`**: the `migrate-staging` / `migrate-production`
  job runs `supabase db push` against that environment's project **before** the Railway
  services deploy. It's a no-op when nothing is pending. A migration failure fails the job
  and blocks the deploy.

So the normal flow is: merge the PR to `main` → promote `main` → `staging` (migration applies
to the staging branch, then services deploy) → promote `staging` → `production` (applies to
production, then deploys).

## Non-additive changes (`DROP` / `RENAME` / type narrowing)

`.github/scripts/railway-deploy.sh` deploys the three backend services sequentially over
several minutes, and `db push` runs ahead of all of them — so for that whole window, old
code runs against the new schema. A `DROP COLUMN` in the same push as the code that stops
writing that column means a still-running old process writes to a column that's already
gone.

The safe sequence is multiple PRs across multiple deploys:

1. Add the replacement column (additive).
2. Deploy code that dual-writes old + new.
3. Backfill, cut all reads over to the new column, deploy.
4. Once that deploy is **confirmed live** in the target environment, a separate PR with just
   the `DROP`. Its migration file carries a `-- non-additive: <reason>` line (which is what
   lets it past `check-migrations.mjs`), and the PR description says how it's sequenced.

`db push` still applies the drop automatically once that final PR promotes — the discipline
is in *when* you merge it, not in applying it by hand.

## If CI can't apply a migration

Apply it directly with the same tool CI uses:

```
supabase db push --db-url "<session-pooler connection string>" --yes
```

The connection strings are the `SUPABASE_DB_URL_STAGING` / `SUPABASE_DB_URL_PRODUCTION`
GitHub secrets (Supabase dashboard → Connect → **Session pooler**, password percent-encoded).

If `db push` reports the local files and the remote history have diverged, reconcile the
history table (this rewrites tracking rows only, runs no DDL):

```
supabase migration list   --db-url "<url>"          # see the divergence
supabase migration repair --db-url "<url>" --status applied   <version> …
supabase migration repair --db-url "<url>" --status reverted  <version> …
```
