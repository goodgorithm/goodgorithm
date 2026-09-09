<!-- See CONTRIBUTING.md's Pull requests section for the full process. -->

Closes #

## What this does

<!-- Brief description -- the why, not just a restatement of the diff. -->

## Checklist

- [ ] Branch is named `bug/issue-#-description`, `feature/issue-#-description`, or `chore/issue-#-description`
- [ ] Opened against `main`, not `staging`/`production`
- [ ] CI passes (`processing/` pytest; `ingestion/`/`api/`/`web/` build + test)
- [ ] If this touches `web/`, ran `npm run lint` locally (not wired into CI yet)
- [ ] If this adds a migration: it's additive-only, or it carries a `-- non-additive: <reason>` line and a note here on how it's sequenced across deploys (see `doc/MIGRATIONS.md`)
