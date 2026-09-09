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

3. **R2**: don't configure it. Leave the `R2_MODELS_*` vars unset in `processing/.env` — this is the normal local-dev path, not a shortcut. Tell the user this means VADER/keyword-taxonomy fallbacks, not the real trained models.

4. **Wire `.env` per service** — three separate files, each in its own service directory (not a shared root `.env`):
   - `ingestion/.env`: `DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres`, `BLUESKY_SAMPLE_RATE=0.05`
   - `processing/.env`: same `DATABASE_URL`, `REDIS_URL=redis://localhost:6379`, `PROCESSING_BATCH_SIZE=20`, `PROCESSING_INTERVAL_SECONDS=60`, `PORT=8081` (keeps the long-lived loop's status server off `ingestion/`'s `8080`; harmless for `--once`)
   - `api/.env`: same `DATABASE_URL`
   - `web/.env`: `cp web/.env.example web/.env` if it doesn't already exist (default `VITE_API_BASE_URL=http://localhost:3000` is already correct)
   Only create files that don't already exist — never overwrite an existing `.env` without asking first, it may hold values the user set deliberately.

5. **Ingestion**: `cd ingestion && npm install && npm run dev` (background it). Checkpoint: `curl -s localhost:8080/health | python3 -m json.tool` shows connection state; after ~30-60s, `docker exec supabase_db_goodgorithm psql -U postgres -c "select count(*) from raw_posts;"` should show a rising count.

6. **Processing**: `cd processing && uv sync && uv run python src/main.py --once`. Checkpoint: console output shows `processed N posts` with no errors; `docker exec supabase_db_goodgorithm psql -U postgres -c "select count(*) from processed_posts where rank_score is not null;"` should be > 0. If it's 0, re-run `--once` a couple more times (ingestion accumulates backlog in the background) before treating it as a real problem.

7. **API**: `cd api && npm install && npm run dev` (background it). Checkpoint: `curl -s localhost:3000/health` → `"reachable": true`, then `curl -s "localhost:3000/v1/feed" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['posts']))"` (**no `category=` param**) returns > 0. That's the real end-to-end check — it needs a ranked post, not a categorized one. Don't gate success on the per-category feeds (`?category=science_technology` etc.): the keyword-taxonomy fallback categorizes only ~3% of posts, so all four can read 0 for a long time on a fresh session (see step 9). `?category=all` is not valid at the API (it 400s) — omit the param instead.

8. **Web**: `cd web && npm install && npm run dev` (background it). Report the URL (`http://localhost:5173`) for the user to open themselves — don't try to screenshot/verify visually unless asked; step 7's no-`category` curl check is the real verification.

9. **Known local-only wrinkle, report this proactively, don't wait to be asked**: without R2 (step 3), the keyword-taxonomy category fallback catches far less than the trained classifier — only ~3% of locally-scored posts land in any of the four categories (vs ~two-thirds), and it's lopsided toward `science_technology`. So every category tab in `web/` can show "No posts yet" for the first several minutes — often much longer for `arts_culture`/`food_dining` — while the pipeline is working perfectly. The no-`category` feed (step 7) is what confirms success. If the user wants category tabs populated, they need `ingestion/` **plus** `processing/` as the long-lived loop (`uv run python src/main.py`, no `--once`) running a while: `science_technology` ~10 min, one or two others over the next ~20–40 min, `food_dining` often not within an hour. Running the loop needs `PORT=8081` in `processing/.env` (its 8080 default collides with `ingestion/` → `OSError: [Errno 48] Address already in use`); `--once` doesn't.

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
- **All four category feeds return 0 even after several `--once` runs** — normal on a fresh session: the keyword-taxonomy fallback categorizes ~3% of posts and lags for many minutes. Verify with the no-`category` feed (`curl -s localhost:3000/v1/feed` → > 0) instead; only treat it as broken if *that* is empty after `processing` has ranked posts (`select count(*) from processed_posts where rank_score is not null` > 0). Actual errors in `processing`'s console are the real signal.
- **`processing` long-lived loop exits with `OSError: [Errno 48] Address already in use`** — its status server defaults to `8080`, already held by `ingestion`. Set `PORT=8081` in `processing/.env` (step 4).

## Gotchas

- Each service reads its own `.env` from its own working directory — there is no shared root `.env` that any service actually loads.
- Never overwrite an existing `.env` file without asking — it may hold deliberate values.
- R2 being unset is the *normal* local path, not a degraded fallback to apologize for.
- Plain runbook, no isolated tooling directory — unlike `web/`'s `run-web` skill (which needs Playwright, a real new dependency), this only orchestrates `docker`/`supabase`/`npm`/`uv`, none of which need a new library dependency.
