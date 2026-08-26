---
name: local-dev-setup
description: Set up and run Goodgorithm's full stack locally (Postgres via the Supabase CLI, Redis via a Valkey container, ingestion/processing/api/web wired together) for interactive development, checking prerequisites at each stage and reporting what's working and what isn't. Use when asked to run the app locally, set up a local dev environment, or get Goodgorithm running end-to-end outside staging.
---

# Local development setup

Four independent services plus Postgres plus Redis, with no `docker-compose.yml` tying them together — this skill checks prerequisites, brings each piece up in the right order, and verifies each checkpoint before moving to the next, rather than starting everything at once and hoping.

This skill **follows** the wiki's [Local Development](https://github.com/goodgorithm/goodgorithm/wiki/Local-Development) page step by step — it doesn't re-derive or duplicate it. If the two ever disagree, that page is the source of truth; update it first, then this skill. Read `CLAUDE.md` in the repo root first if you haven't — this assumes the architecture it describes.

## Setup

Check-and-report only — never auto-install anything:

- `docker info` succeeds (not just `docker --version` — the daemon must actually be running). If it fails, tell the user to start Docker Desktop and wait for it, then retry.
- `supabase --version` — if missing, tell the user to `brew install supabase/tap/supabase`.
- `node --version`, `uv --version` — should already be present per `CLAUDE.md`'s Development section.

## Steps

1. **Local Postgres**: `supabase start` from the repo root (`supabase/config.toml` is already committed — no `supabase init` needed). Applies all migrations automatically. Checkpoint: parse its printed output for `DB_URL`/`STUDIO_URL`; confirm via `curl -s http://127.0.0.1:54322 -o /dev/null` isn't meaningful for Postgres (it's not HTTP) — instead run a real query: `docker exec supabase_db_goodgorithm psql -U postgres -c "select count(*) from raw_posts;"` should succeed (any count, even 0).

2. **Local Redis**: `docker run -d --name goodgorithm-valkey -p 6379:6379 valkey/valkey:8-alpine` (skip if a container with that name already exists and is running — check `docker ps` first). Checkpoint: `docker exec goodgorithm-valkey valkey-cli ping` → `PONG`.

3. **R2**: don't configure it. Leave `R2_*` vars unset in `processing/.env` — this is the normal local-dev path, not a shortcut. Tell the user this means VADER/keyword-taxonomy fallbacks, not the real trained models.

4. **Wire `.env` per service** — three separate files, each in its own service directory (not a shared root `.env`):
   - `ingestion/.env`: `DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres`, `BLUESKY_SAMPLE_RATE=0.05`
   - `processing/.env`: same `DATABASE_URL`, `REDIS_URL=redis://localhost:6379`, `PROCESSING_BATCH_SIZE=20`, `PROCESSING_INTERVAL_SECONDS=60`
   - `api/.env`: same `DATABASE_URL`
   - `web/.env`: `cp web/.env.example web/.env` if it doesn't already exist (default `VITE_API_BASE_URL=http://localhost:3000` is already correct)
   Only create files that don't already exist — never overwrite an existing `.env` without asking first, it may hold values the user set deliberately.

5. **Ingestion**: `cd ingestion && npm install && npm run dev` (background it). Checkpoint: `curl -s localhost:8080/health | python3 -m json.tool` shows connection state; after ~30-60s, `docker exec supabase_db_goodgorithm psql -U postgres -c "select count(*) from raw_posts;"` should show a rising count.

6. **Processing**: `cd processing && uv sync && uv run python src/main.py --once`. Checkpoint: console output shows `processed N posts` with no errors; `docker exec supabase_db_goodgorithm psql -U postgres -c "select count(*) from processed_posts where rank_score is not null;"` should be > 0. If it's 0, re-run `--once` a couple more times (ingestion accumulates backlog in the background) before treating it as a real problem.

7. **API**: `cd api && npm install && npm run dev` (background it). Checkpoint: `curl -s localhost:3000/health` → `"reachable": true`. Then check across all four categories, since one may still be empty (see step 9): `for c in science_technology arts_culture food_dining diaries_daily_life; do echo -n "$c: "; curl -s "localhost:3000/v1/feed?category=$c" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['posts']))"; done` — at least one should be > 0.

8. **Web**: `cd web && npm install && npm run dev` (background it). Report the URL (`http://localhost:5173`) for the user to open themselves — don't try to screenshot/verify visually unless asked; step 7's curl check is the real verification.

9. **Known local-only wrinkle, report this proactively, don't wait to be asked**: without R2 (step 3), the keyword-taxonomy category fallback is noticeably less confident than the trained classifier — most locally-scored posts end up with an empty `category`, matching none of the four tabs. So it's normal and expected for some category tabs (possibly the default one) to show "No posts yet" in `web/` even once everything is genuinely working. Step 7's per-category curl loop is what actually confirms success, not "the default tab has content."

## What this can't do

Bluesky Jetstream and Mastodon's public timelines are always-live, unauthenticated endpoints — there's no local mock or offline mode for either, and this skill doesn't attempt to fake one (`web/`'s `run-web` skill mocks a whole `api/` instance for frontend-only work, which is a different, narrower use case — not reusable here since `ingestion`/`processing`/`api` all need to run for real). This means real data only shows up on the real internet's own timing.

`training/` (model training/release) is explicitly out of scope for this skill — see `.claude/skills/release-sentiment-model/` and `.claude/skills/release-category-classifier/` for that separate, occasional workflow.

## Troubleshooting

- **`Cannot connect to the Docker daemon at unix:///.../docker.sock`** — Docker Desktop isn't running; start it, wait for the daemon, retry.
- **`supabase start` reports a port already allocated** (54321-54324) — another local stack or a stray Postgres is bound to it; `supabase stop` first, or `lsof -iTCP -sTCP:LISTEN` to find the culprit.
- **`command not found: supabase`** — `brew install supabase/tap/supabase`.
- **`EADDRINUSE` on 6379** — a stray Redis/Valkey is already listening (`docker ps`, or `lsof -ti:6379 -sTCP:LISTEN`).
- **`EADDRINUSE` on 3000 / 8080 / 5173** — a previous run's `api`/`ingestion`/`web` dev server is still up: `lsof -ti:<port> -sTCP:LISTEN | xargs -r kill`.
- **`DATABASE_URL is required`** (from `ingestion`/`api`) — that service's own `.env` wasn't created (step 4); a root `.env` doesn't count.
- **`missing required env vars: DATABASE_URL, REDIS_URL`** (from `processing`) — same, for `processing/.env`.
- **No rows in `raw_posts` after a couple of minutes** — expected sometimes; `BLUESKY_SAMPLE_RATE` is probabilistic. Wait longer before treating it as broken.
- **All four categories return 0 posts even after several `--once` runs** — genuinely worth investigating (check `processing`'s console output for errors); one category having 0 is normal, all four is not.

## Gotchas

- Each service reads its own `.env` from its own working directory — there is no shared root `.env` that any service actually loads.
- Never overwrite an existing `.env` file without asking — it may hold deliberate values.
- R2 being unset is the *normal* local path, not a degraded fallback to apologize for.
- Plain runbook, no isolated tooling directory — unlike `web/`'s `run-web` skill (which needs Playwright, a real new dependency), this only orchestrates `docker`/`supabase`/`npm`/`uv`, none of which need a new library dependency.
