# Security policy

Goodgorithm is a small, mostly-static project — there's no bug bounty and no formal SLA, but security reports are taken seriously and get a real response.

## Reporting a vulnerability

Two ways, pick whichever you're more comfortable with:

- **[GitHub private vulnerability reporting](https://github.com/goodgorithm/goodgorithm/security/advisories/new)** — the preferred channel. It's a private conversation visible only to you and the maintainers, and keeps the report attached to the repo if it turns into an advisory.
- **Email [security@goodgorithm.com](mailto:security@goodgorithm.com)** — if you'd rather not use GitHub, or the issue involves something outside this repo (e.g. infrastructure, not code).

Please don't open a public issue for a security report — everything in this repo's issue tracker is public by design (see `CONTRIBUTING.md`), which isn't appropriate for a vulnerability that hasn't been fixed yet.

## What to include

Whatever you have that would help reproduce or understand the issue: the affected service (`ingestion/`, `processing/`, `api/`, `web/`, etc.), steps to reproduce, and the potential impact as you understand it. A proof of concept is welcome but not required to report something.

## What to expect

An acknowledgment as soon as we see it — this is a small project, not a 24/7 operation, so that may not be immediate, but it won't be ignored. From there, we'll work with you on understanding the issue and getting a fix out; timelines depend on severity and complexity, not a fixed SLA.

## Scope

This covers the code and infrastructure in this repo and its deployed services (Railway, Cloudflare, Supabase, Upstash — see `CLAUDE.md`'s Infra section). It doesn't cover the third-party platforms Goodgorithm reads from (Bluesky, Mastodon) — report issues with those platforms themselves to their own security teams.
