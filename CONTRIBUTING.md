# Contributing

If you're reading this because you're thinking about contributing: welcome, and thank you. This project only works if the algorithm is something people can actually trust, which means the code behind it has to hold up to scrutiny — see [`MISSION.md`](MISSION.md) for the values and principles that review bar comes from. Read that first if you haven't; it's not decoration, it's the actual standard your contribution gets checked against.

One thing worth knowing going in, in the same spirit of transparency: a meaningful share of this codebase has been built with AI pair-programming (Claude Code), openly and on purpose. That's expected to continue, including for reviewing contributions — don't be surprised if Claude is part of the process on the other side of a PR too.

**Not yet actually open for outside contributions** (see the README) — the rest of this doc describes the process for when that changes, and is also the working process for whoever *is* touching the repo today, human or Claude, so issues and branches stay predictable as the project grows. Interactions here are also governed by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Dev setup

Covered in [`CLAUDE.md`'s Development section](CLAUDE.md#development) — per-service install/run/build/test commands. Not repeated here.

## Issue types

Every issue gets exactly one type, via GitHub label:

- **Bug** — label `bug`.
- **Feature** — label `enhancement` (GitHub's default label already covers this — "New feature or request" — so we're reusing it rather than adding a redundant `feature` label).

That's the whole taxonomy for now, deliberately. No other type labels (`question`, `documentation`, etc.) until the two-type split actually stops being enough — easier to add one later than to unwind label sprawl.

## Branches

Work resolving an issue happens on a branch named:

```
bug/issue-<#>-<short-description>
feature/issue-<#>-<short-description>
```

e.g. `bug/issue-1-redis-capacity-crash`, `feature/issue-4-category-filter`.

All of these branches merge into `main`. From there, promotion to `staging` and `production`, commit message format, and the `Co-Authored-By` convention are covered in [`CLAUDE.md`'s Git conventions](CLAUDE.md#git-conventions) — not repeated here, to avoid the two drifting out of sync.

## Picking up an issue

Before starting work, comment on the issue saying you're picking it up — this is the only signal anyone else has that it's in progress, so skipping it risks duplicate work. If your bandwidth is uncertain, say so in the same comment (e.g. "picking this up, but slowly — jump in if you get to it faster") rather than silently sitting on it.

## Coding conventions

No separate style guide — what CI actually checks (below) is the real bar. Beyond that, match what's already in the file you're touching: this codebase leans toward small, focused functions over abstraction, and comments that explain a non-obvious *why* (a workaround, a trade-off, an incident that shaped the code) rather than restating *what* the code already says. If you're unsure, look at how a neighboring function in the same file is written and follow it, rather than introducing a new pattern.

## What CI checks

`.github/workflows/ci.yml`, on every push and PR to `main`/`staging`/`production`:

- `processing/`: `uv run pytest`.
- `ingestion/`, `api/`, `web/`: `npm run build` (type-check + compile) and `npm test`.

Pushes to `staging`/`production` additionally deploy (Railway for `ingestion`/`api`/`processing`, Cloudflare Workers for `web/`) once the above passes — see [`CLAUDE.md`'s Git conventions](CLAUDE.md#git-conventions) for the branch-promotion flow that triggers this.

`web/`'s `npm run lint` (oxlint) exists as a local script but isn't wired into CI yet — run it yourself before opening a PR that touches `web/`.

## Pull requests

- One issue per branch, per the naming convention above.
- Open the PR against `main`, not `staging`/`production` — those are promotion targets, not integration branches (see Git conventions).
- CI has to pass before merge.
- Reference the issue number in the PR description (e.g. `Closes #12`) so it closes automatically on merge.

GitHub surfaces the policies above automatically: opening an issue picks between `.github/ISSUE_TEMPLATE/bug_report.md` and `feature_request.md` (blank issues are disabled, so the type choice is structural, not just a written rule), and `.github/PULL_REQUEST_TEMPLATE.md` pre-fills the checklist above on every PR.
