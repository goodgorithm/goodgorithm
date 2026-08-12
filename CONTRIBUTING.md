# Contributing

Not yet open for outside contributions (see the README) — this doc is the working process for whoever *is* touching the repo, human or Claude, so issues and branches stay predictable as the project grows.

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
