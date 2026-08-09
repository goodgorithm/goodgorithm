# Goodgorithm — project context

Read this before starting work. It's the condensed version of decisions made in planning and in code; the full history lives in Notion (links at the bottom).

## What this is

An open-source, free-forever, ad-free algorithmic feed of positive/uplifting public social posts. The pitch: counter the negativity bias of mainstream platform algorithms, and reclaim "algorithm" from its usual "platform manipulating you" connotation.

**Status:** early development. `ingestion/`, `processing/`, and `api/` are built, tested, and deployed to `staging` and `production` on Railway. No web frontend yet — that's the next major piece of work, once the pipeline has run against enough real data to be worth building a UI on top of.

## Two constraints that are load-bearing, not aspirational

**1. No LLM in the algorithm itself.** Content selection (sentiment scoring, topic/newsworthiness detection, ranking) runs on classic ML: TF-IDF, spaCy NER, MinHash/LSH, a small CNN over word embeddings for sentiment. Not an LLM. The reasoning: the whole pitch is "trust why a post got selected," and classical ML is small, auditable, and doesn't drift or hallucinate the way an LLM can. This is specifically about what powers the algorithm — it does not extend to how the project is built. LLM tools (including Claude) are used openly for development, research, and docs. Don't blur this distinction in code comments, docs, or commit messages: "no LLMs in the filter," not "no LLMs anywhere."

**2. No engagement signals in ranking.** The ranking/dedup pipeline must never read likes, reposts, replies, or follower counts from the source platform. An earlier draft violated this (used an HN-style upvote-decay formula) and got caught and rewritten — see the Decisions Log for what happened. `processing/src/ranking.py`'s `compute_base_score` is the literal enforcement of this: `positivity(sentiment) × topicality × recency_decay`, no other fields exist on `RankablePost` for this to accidentally read. Bot-filtering (`bot_filter.py`) is allowed but stays defensive-only — a hard eligibility filter, never a score boost, so it can't become a backdoor engagement signal.

## Architecture (as built)

Four services, each independently deployable:

| Path | Language | Deployed as | What it does |
|---|---|---|---|
| `ingestion/` | TypeScript | Railway service `goodgorithm-ingestion` | Long-lived process: Bluesky Jetstream WebSocket + Mastodon polling → `raw_posts` in Postgres. |
| `processing/` | Python | Railway service `goodgorithm-processing` | Long-lived loop: dedup → bot filter → topicality → sentiment → base score → MMR ranking → `processed_posts`. |
| `api/` | TypeScript (Fastify) | Railway service `goodgorithm-api` | Stateless, read-only, unauthenticated HTTP. `/feed` (cursor-paginated, ordered by `rank_score`), `/health`. |
| `training/` | Python (notebook) | Run manually on Colab/Kaggle, not deployed | Trains the sentiment CNN, exports to ONNX, publishes versioned artifacts to R2. |

Schema lives in `supabase/migrations/` (`raw_posts`, `processed_posts`, applied via Supabase's migration tooling — don't hand-edit the schema elsewhere).

**For the exact step-by-step mechanics of every pipeline stage** (thresholds, formulas, why each one works the way it does), see the published **Algorithm** page in Notion (link at the bottom) — that's the canonical, kept-current explanation. Don't duplicate it at length here; it'll drift.

### Data flow

```
Bluesky Jetstream ─┐
                    ├─> ingestion/ ─> raw_posts ─> processing/ ─> processed_posts ─> api/ ─> /feed
Mastodon polling ───┘                  (dedup, bot filter, topicality,
                                         sentiment, base score, MMR rank)
```

`raw_posts` and `processed_posts` are separate tables, joined at read time — nothing is ever mutated in `raw_posts` after ingestion, so the original data is always intact for audit/replay even as scoring logic evolves.

### Sentiment model loading

`processing/` tries once per process to load the trained CNN from R2 (`sentiment-cnn/latest.json` → versioned `model.onnx`/`vocab.json`/`config.json`); on any failure (R2 not configured, network error, nothing published yet) it falls back to VADER and keeps running. `sentiment_method` on every scored post records which one actually produced that score. To train and publish a new model version, use the `release-sentiment-model` skill (`.claude/skills/release-sentiment-model/`) rather than improvising the R2 upload — it covers the tokenizer commit-pinning requirement and the versioned/gated-promotion release process.

### Data retention

Alpha-stage cap, not a correctness requirement: both Postgres and Redis only retain the last 24 hours of data. `processing/src/pipeline.py`'s `RETENTION_HOURS = 24` drives a `cleanup_old_data()` step that runs every cycle, deleting `raw_posts` older than the cutoff; `processed_posts` rows cascade-delete via FK (`supabase/migrations/0003_cascade_delete_processed_posts.sql`). Redis TTLs for dedup (`BAND_TTL_SECONDS`, `dedup.py`) and bot-filter self-dup tracking (`SELF_DUP_TTL_SECONDS`, `bot_filter.py`) are aligned to the same 24h window — no point holding LSH/dedup state for posts that no longer exist in Postgres.

Note `ranking.py`'s `MMR_WINDOW_HOURS` is still `72.0` in code but is now effectively capped at 24h by retention (a post can't survive long enough to hit the 72h boundary) — left as-is rather than changed, so it becomes meaningful again automatically if retention is raised post-alpha. Don't "fix" this mismatch without checking the Decisions Log entry first.

As of 2026-08-09 migration 0003 is applied on both the Supabase `staging` branch and `production`, and the retention code is committed on `main`, but not yet promoted through `staging`/`production` or deployed to Railway. Check actual state (`git log`, Supabase migration list, Railway deploy status) before assuming this is live everywhere — code/infra changes now happen via Claude Code, not this session, so this file may lag reality until the next doc sync.

## Data sources

Bluesky Jetstream (public WebSocket firehose, filtered to `app.bsky.feed.post` creates) and Mastodon public timelines (polling `fosstodon.org` + `hachyderm.io`, 30s interval). Both are open, unauthenticated protocols — no paid APIs, no scraping behind logins. English-only on both paths; every downstream model is English-only. This is deliberate: keeps the pipeline reproducible without special access.

## Infra (provisioned and live)

- **Cloudflare** — DNS, R2 for object storage (bucket `goodgorithm-models`: model checkpoints, datasets, transparency samples), Pages for the PWA (not built yet).
- **Railway** — project `goodgorithm`, three services (`goodgorithm-ingestion`, `goodgorithm-processing`, `goodgorithm-api`), each with `staging` and `production` environments.
- **Supabase** — Postgres. Production project + a `staging` branch off it. Migrations applied via `supabase/migrations/`.
- **Upstash** — serverless Redis, REST API (not raw `redis://`). Ephemeral, TTL'd state only: LSH bands + MinHash signatures (dedup), author velocity + self-dup tracking (bot filter), entity burst counters (topicality). Postgres holds every durable result; Redis is disposable.
- **GitHub** — this repo, org `goodgorithm`. Three long-lived branches (`main` → `staging` → `production`), mirroring the Railway/Supabase environment promotion flow — see Git conventions below.

Env var names are documented in `.env.example` at the repo root — never commit actual values. Real values live in Railway's environment variables (set separately per service, per environment) and nowhere else in this repo. Each service only needs a subset — `ingestion/` and `api/` just need `DATABASE_URL`; `processing/` additionally needs the Redis and R2 vars.

## Development

Each service is independent — install/run/test from within its own directory.

- **`ingestion/`, `api/`** (Node/TypeScript): `npm install`, `npm run dev` (watch mode via `tsx`), `npm run build` (type-check + compile), `npm test` (`api/` only, uses Node's built-in test runner).
- **`processing/`** (Python, managed with `uv`): `uv sync`, `uv run python src/main.py --once` (single cycle, for local testing) or without `--once` for the long-lived loop, `uv run pytest` (unit tests — many run without any real DB/Redis/R2 credentials, since `config.validate()` is only called explicitly from entrypoints, not at import time).
- **`training/sentiment_cnn.ipynb`**: not run locally — needs a GPU. Open in Colab or Kaggle. See the `release-sentiment-model` skill before touching this.

CI (`.github/workflows/ci.yml`) runs `processing`'s pytest suite, and builds/tests `ingestion`/`api`, on every push and PR to `main`/`staging`/`production`.

## Git conventions

- Commit messages: plain, descriptive. Include a `Co-Authored-By: Claude <noreply@anthropic.com>` trailer on commits produced by/with Claude (not required retroactively on the very first commit).
- Three long-lived branches, promoted in sequence: feature branches merge into `main` first; `main` promotes to `staging`; `staging` promotes to `production`. `staging` and `production` map directly to the matching Railway/Supabase environments — `main` itself isn't deployed anywhere, it's just the integration branch. CI runs tests/build on all three branches; pushes to `staging`/`production` additionally trigger a deploy to the matching Railway environment (per-service) once CI passes.

## Docs

This file is the condensed bridge for coding sessions. Full project documentation lives in Notion, not in this repo:

- **Published, public docs** ("Goodgorithm — Public Docs") — distilled, publish-safe docs meant for users/contributors: [Algorithm](https://app.notion.com/p/3b79243701a781a8997ed17609a60bc7) (step-by-step pipeline mechanics — the detailed companion to the "Architecture" section above) and [Infrastructure](https://app.notion.com/p/3b69243701a78144b4fafb22665c07b2) (hosting/tooling and why). Link new user-facing docs here, not in the internal workspace.
- **Internal workspace** ("Goodgorithm Docs") — Decisions Log (including implementation-phase decisions and known gaps), Project Research, Infrastructure Plan (with pricing/account specifics), MVP Setup Checklist. Private, not for external sharing.

If you have the Notion MCP connector available and need more context than this file provides (exact rationale for a past decision, full pricing research, etc.), check the internal workspace first.
