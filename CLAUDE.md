# Goodgorithm — project context

Read this before starting work. It's the condensed version of decisions made in planning; the full history lives in Notion (links at the bottom).

## What this is

An open-source, free-forever, ad-free algorithmic feed of positive/uplifting public social posts. The pitch: counter the negativity bias of mainstream platform algorithms, and reclaim "algorithm" from its usual "platform manipulating you" connotation.

**Status:** pre-alpha. Infra is provisioned (see below) but no pipeline code exists yet. First build target is data ingestion, validated against real data, before pipeline or web work starts.

## Two constraints that are load-bearing, not aspirational

**1. No LLM in the algorithm itself.** Content selection (sentiment scoring, topic/newsworthiness detection, ranking) runs on classic ML: TF-IDF, spaCy NER, a small CNN over word embeddings for sentiment. Not an LLM. The reasoning: the whole pitch is "trust why a post got selected," and classical ML is small, auditable, and doesn't drift or hallucinate the way an LLM can. This is specifically about what powers the algorithm — it does not extend to how the project is built. LLM tools (including Claude) are used openly for development, research, and docs. Don't blur this distinction in code comments, docs, or commit messages: "no LLMs in the filter," not "no LLMs anywhere."

**2. No engagement signals in ranking.** The ranking/dedup pipeline must never read likes, reposts, replies, or follower counts from the source platform. An earlier draft violated this (used an HN-style upvote-decay formula) and got caught and rewritten — see the Decisions Log for what happened. Ranking signals must be content-derived only: positivity strength × topicality/burst score × recency decay, plus MMR for diversity re-ranking. Bot-filtering is allowed but must stay defensive-only (a filter, never a ranking boost) — it can't smuggle engagement-style signals back in.

## Data sources

Bluesky Jetstream (public WebSocket firehose) and Mastodon public timelines. Both are open, unauthenticated protocols — no paid APIs, no scraping behind logins. This is deliberate: keeps the pipeline reproducible without special access.

## Algorithm pipeline (planned shape)

1. **Ingestion** — long-lived process consuming Jetstream + polling Mastodon. Always-on, not request-triggered.
2. **Processing** — dedup (MinHash/LSH), sentiment CNN, NER + TF-IDF burst scoring for topicality, bot filter, ranking (see constraint #2 above).
3. **API/backend** — serves the ranked feed. Stateless HTTP.
4. **ML training** — periodic (not continuous) fine-tuning of the sentiment CNN. Small model, runs fine on free-tier GPU notebook quotas (Colab/Kaggle). Inference is CPU-only.

## Infra (already provisioned)

- **Cloudflare** — DNS, R2 for object storage (bucket `goodgorithm-models`: model checkpoints, datasets, transparency samples), Pages for the PWA (not built yet).
- **Railway** — service `goodgorithm`, with separate `production` and `staging` environments. Runs (or will run) ingestion + pipeline + API.
- **Supabase** — Postgres. Production project + a `staging` branch off it.
- **Upstash** — serverless Redis, REST API (not raw `redis://`). For burst-detection counters and dedup signature lookups.
- **GitHub** — this repo, org `goodgorithm`. Three long-lived branches (`main` → `staging` → `production`), mirroring the Railway/Supabase environment promotion flow — see Git conventions below.

Env var names are documented in `.env.example` — never commit actual values. Real values live in Railway's environment variables (set separately per environment) and nowhere else in this repo.

## Git conventions

- Commit messages: plain, descriptive. Include a `Co-Authored-By: Claude <noreply@anthropic.com>` trailer on commits produced by/with Claude (not required retroactively on the very first commit).
- Three long-lived branches, promoted in sequence: feature branches merge into `main` first; `main` promotes to `staging`; `staging` promotes to `production`. `staging` and `production` map directly to the matching Railway/Supabase environments — `main` itself isn't deployed anywhere, it's just the integration branch. CI (`.github/workflows/ci.yml`) runs tests/build on all three branches; pushes to `staging`/`production` additionally trigger a deploy to the matching Railway environment once CI passes.

## Docs

This file is the condensed bridge for coding sessions. Full project documentation lives in Notion, not in this repo:

- **Internal workspace** ("Goodgorithm Docs") — Decisions Log, Project Research (algorithm landscape scan, naming), Infrastructure Plan (with pricing/account specifics), MVP Setup Checklist. Private, not for external sharing.
- **Public workspace** ("Goodgorithm — Public Docs") — distilled, publish-safe docs meant for users/contributors, e.g. the [Infrastructure](https://app.notion.com/p/3b69243701a78144b4fafb22665c07b2) page. Link new user-facing docs here, not in the internal workspace.

If you have the Notion MCP connector available and need more context than this file provides (exact rationale for a past decision, full pricing research, etc.), check the internal workspace first.
