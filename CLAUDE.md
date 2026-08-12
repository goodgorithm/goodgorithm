# Goodgorithm — project context

Read this before starting work. It's the condensed version of decisions made in planning and in code; the full history lives in Notion (links at the bottom).

## What this is

An open-source, free-forever, ad-free algorithmic feed of positive/uplifting public social posts. The pitch: counter the negativity bias of mainstream platform algorithms, and reclaim "algorithm" from its usual "platform manipulating you" connotation.

**Status:** early development. `ingestion/`, `processing/`, and `api/` are built, tested, and deployed to `staging` and `production` on Railway. `web/` (PWA frontend) is built and passing CI, but not deployed yet — needs a one-time Cloudflare Workers account setup (create the `goodgorithm-web` Worker, add a `CLOUDFLARE_API_TOKEN` repo secret) before `deploy-web-staging`/`deploy-web-production` in `ci.yml` can actually ship it.

## Two constraints that are load-bearing, not aspirational

**1. No LLM in the algorithm itself.** Content selection (sentiment scoring, topic/newsworthiness detection, ranking) runs on classic ML: TF-IDF, spaCy NER, MinHash/LSH, a small CNN over word embeddings for sentiment. Not an LLM. The reasoning: the whole pitch is "trust why a post got selected," and classical ML is small, auditable, and doesn't drift or hallucinate the way an LLM can. This is specifically about what powers the algorithm — it does not extend to how the project is built. LLM tools (including Claude) are used openly for development, research, and docs. Don't blur this distinction in code comments, docs, or commit messages: "no LLMs in the filter," not "no LLMs anywhere."

**2. No engagement signals in ranking.** The ranking/dedup pipeline must never read likes, reposts, replies, or follower counts from the source platform. An earlier draft violated this (used an HN-style upvote-decay formula) and got caught and rewritten — see the Decisions Log for what happened. `processing/src/ranking.py`'s `compute_base_score` is the literal enforcement of this: `positivity(sentiment) × topicality × recency_decay`, no other fields exist on `RankablePost` for this to accidentally read. Bot-filtering (`bot_filter.py`) is allowed but stays defensive-only — a hard eligibility filter, never a score boost, so it can't become a backdoor engagement signal.

## Architecture (as built)

Five services, each independently deployable:

| Path | Language | Deployed as | What it does |
|---|---|---|---|
| `ingestion/` | TypeScript | Railway service `goodgorithm-ingestion` | Long-lived process: Bluesky Jetstream WebSocket + Mastodon polling → `raw_posts` in Postgres. |
| `processing/` | Python | Railway service `goodgorithm-processing` | Long-lived loop: content filter → dedup → bot filter → topicality → quote resolution → sentiment → base score → MMR ranking → `processed_posts`. |
| `api/` | TypeScript (Fastify) | Railway service `goodgorithm-api` | Stateless, read-only, unauthenticated HTTP — no outbound calls of its own (see Post attachments & embeds below). `/feed` (cursor-paginated, ordered by `rank_score`), `/health`. |
| `web/` | TypeScript (React + Vite) | Cloudflare Workers static assets (`goodgorithm-web`, staging/production named environments) — not yet deployed, see Status above | PWA: infinite-scroll feed consuming `api/`'s `/feed`, no accounts/personalization. `VITE_API_BASE_URL` baked in at build time (static site, no server component). |
| `training/` | Python (notebook) | Run manually on Colab/Kaggle, not deployed | Trains the sentiment CNN, exports to ONNX, publishes versioned artifacts to R2. |

Schema lives in `supabase/migrations/` (`raw_posts`, `processed_posts`, applied via Supabase's migration tooling — don't hand-edit the schema elsewhere).

**For the exact step-by-step mechanics of every pipeline stage** (thresholds, formulas, why each one works the way it does), see the published **Algorithm** page in Notion (link at the bottom) — that's the canonical, kept-current explanation. Don't duplicate it at length here; it'll drift.

### Data flow

```
Bluesky Jetstream ─┐
                    ├─> ingestion/ ─> raw_posts ─> processing/ ─> processed_posts ─> api/ ─> /feed ─> web/
Mastodon polling ───┘                  (dedup, bot filter, topicality,
                                         sentiment, base score, MMR rank)
```

`raw_posts` and `processed_posts` are separate tables, joined at read time — nothing is ever mutated in `raw_posts` after ingestion, so the original data is always intact for audit/replay even as scoring logic evolves.

### Sentiment model loading

`processing/` tries once per process to load the trained CNN from R2 (`sentiment-cnn/latest.json` → versioned `model.onnx`/`vocab.json`/`config.json`); on any failure (R2 not configured, network error, nothing published yet) it falls back to VADER and keeps running. `sentiment_method` on every scored post records which one actually produced that score. To train and publish a new model version, use the `release-sentiment-model` skill (`.claude/skills/release-sentiment-model/`) rather than improvising the R2 upload — it covers the tokenizer commit-pinning requirement and the versioned/gated-promotion release process.

### Data retention

Alpha-stage cap, not a correctness requirement: both Postgres and Redis only retain the last 24 hours of data. `processing/src/pipeline.py`'s `RETENTION_HOURS = 24` drives a `cleanup_old_data()` step that runs every cycle, deleting `raw_posts` older than the cutoff; `processed_posts` rows cascade-delete via FK (`supabase/migrations/0003_cascade_delete_processed_posts.sql`). Redis TTLs for dedup (`BAND_TTL_SECONDS`, `dedup.py`) and bot-filter self-dup tracking (`SELF_DUP_TTL_SECONDS`, `bot_filter.py`) are aligned to the same 24h window — no point holding LSH/dedup state for posts that no longer exist in Postgres.

Note `ranking.py`'s `MMR_WINDOW_HOURS` is still `72.0` in code but is now effectively capped at 24h by retention (a post can't survive long enough to hit the 72h boundary) — left as-is rather than changed, so it becomes meaningful again automatically if retention is raised post-alpha. Don't "fix" this mismatch without checking the Decisions Log entry first.

Migration 0003 has been applied and the retention code deployed on both `staging` and `production` since 2026-08-10. As with any infra/deploy state, check actual state (`git log`, Supabase migration list, Railway deploy status) before assuming this file is current — code/infra changes happen via Claude Code across many sessions, so this file can lag reality between doc syncs.

### Post attachments & embeds

`api/src/attachments.ts` parses each post's images, link cards, video, and quote-post content into a normalized `Attachment[]` the frontend renders — the `Attachment` union is hand-duplicated in `web/src/api/types.ts` (no shared package across the API/web boundary in this repo). Images and link cards are pure string-templating off `raw_json` (Bluesky's CDN URLs, Mastodon's own media URLs) with zero network calls at serve time.

Video (added 2026-08-10) follows the same pure-templating pattern: Bluesky's raw video embed only has a blob ref (CID), but the HLS playlist URL is deterministically constructable client-side as `https://video.bsky.app/watch/{did}/{videoCid}/playlist.m3u8` — no AppView call, `api/` stays untouched architecturally. Mastodon's `video`/`gifv` media are already-playable URLs. `web/`'s `VideoPlayer.tsx` uses `hls.js` as a non-Safari fallback for the `.m3u8` URLs (native `<video>` handles Mastodon's plain MP4s and Safari's native HLS directly); GIF-like video (Bluesky `presentation: "gif"`, Mastodon `gifv`) autoplays muted/looping/no-controls, regular video requires a tap.

Quote-post content resolution (added 2026-08-10) is the one piece that isn't pure templating — a Bluesky quote embed only ever carries `{cid, uri}`, so showing the quoted post's own text/author needs a live call to Bluesky's public, unauthenticated AppView (`app.bsky.feed.getPosts`, batched up to 25 URIs/call). This resolution happens in `processing/src/quote_resolver.py` at scoring time, not in `api/` — `processing/`'s first outbound network dependency, deliberately placed there rather than in `api/` so `api/` stays stateless/DB-in-JSON-out, and so quoted content can be run through the same `content_filter.is_content_excluded()` checks a regular post gets before it's ever stored (a quoted post carries its own moderation status independent of the post quoting it — Decisions Log: precision over recall). The result is a pre-shaped, already-filtered blob on a nullable `processed_posts.quote_content` column that `api/` passes straight through with no further shaping. Deliberately never reads or stores the engagement counts (`likeCount`/`repostCount`/etc.) that `getPosts`' response includes — no engagement signals anywhere in the product, not just ranking. A quoted post absent from a successful response (deleted/blocked/detached — `getPosts` doesn't distinguish which) resolves to an explicit `not_found` status; a network/API failure just leaves `quote_content` null for that post, with no retry, since each `raw_post` is only ever scored once.

### Category filtering

Added 2026-08-11, closing the Pre-v1 Roadmap's "Categories / topic filter view" item. Rule/keyword-based, not a trained classifier — stays classical ML per the no-LLM-in-the-algorithm constraint, since topic detection is explicitly named in that constraint already. Eight fixed categories (Technology, Arts & Culture, Animals, Science & Discovery, Kindness & Community, Environment & Nature, Health & Recovery, Sports & Achievement), chosen via a triangulated research pass (IPTC Media Topics + good-news-outlet precedent + real production entity/keyword volume) rather than gut feel — full rationale in the Decisions Log/taxonomy artifact linked from the Pre-v1 Roadmap.

`processing/src/topicality.py` now persists entity-type labels and a ranked TF-IDF term list (`TopicalityResult.top_terms`) that used to be discarded; `processing/src/taxonomy.py`'s `categorize()` maps those to a category via a lookup table, called from `pipeline.py` alongside `base_score` — **deliberately not threaded into `ranking.py`/`RankablePost`**, since category is a post-hoc filter on top of the existing rank_score, not a ranking input (same "don't accidentally create a backdoor scoring signal" discipline as the two load-bearing constraints above). Stored on a nullable `processed_posts.category` column (`supabase/migrations/0005_add_category.sql`, indexed as `(category, rank_score DESC, id DESC)` to keep filtered feed queries on the same fast path as the unfiltered one). `api/`'s `/feed` accepts an optional `category` query param (`api/src/categories.ts` validates against the fixed set); `web/`'s `CategorySelector` renders the eight categories plus "Full feed" as a horizontally-scrolling chip row, with scroll-edge fade+chevron indicators (added after a real bug on staging: the row silently overflowed on narrow viewports with no visible scrollbar, so the last chips were present but undiscoverable).

## Performance & staging cost

Tuning pass done 2026-08-11, prompted by staging running `ingestion`/`processing` at full production intensity for no functional need (a Pre-v1 Roadmap item) and a general look for performance issues missed while heads-down on functionality. The single biggest lever, `refresh_rankings()`'s MMR pass rerunning its full O(n²) similarity computation nearly every loop iteration, cost **both** environments, not just staging — so most of this pass is a general perf fix, not a staging-only one.

- `processing/src/main.py`: `refresh_rankings()` is now throttled to a configurable minimum cadence (`REFRESH_RANKINGS_INTERVAL_SECONDS`, default `30`) instead of running unconditionally every loop iteration; the backlog-aware loop's sleep between iterations is now `PROCESSING_BACKLOG_BUFFER_SECONDS` (default `3`, preserving prior behavior) instead of a hardcoded constant.
- `processing/src/topicality.py`: spaCy loads with `parser`/`tagger`/`attribute_ruler` disabled alongside the existing `lemmatizer` disable — only `doc.ents` is ever read, so those pipeline components were dead weight run on every post.
- `processing/src/db.py`/`pipeline.py`: `upsert_processed_posts` batches the per-cycle writes into chunked multi-row `INSERT ... VALUES` (mirroring `update_rank_scores`' existing pattern) instead of one round trip per post.
- `web/src/components/PostAttachments.tsx`: `hls.js`/`VideoPlayer` are now `React.lazy`-loaded, since most posts carry no video and even video-bearing ones on Safari don't need `hls.js` at all — cut the main JS bundle from ~746KB to 238KB (gzip 230KB→74.7KB).
- Staging-only Railway config (no code difference, just lower-intensity settings): `BLUESKY_SAMPLE_RATE=0.01` (vs. production's tuned `0.045`), `PROCESSING_BATCH_SIZE=100`, `PROCESSING_INTERVAL_SECONDS=600`. Deliberately not touched: `DISABLE_LABEL_FILTER` (staging keeps validating the full content-safety pipeline) and Mastodon polling config (already negligible volume).

## Redis capacity

Production `processing` crash-looped starting 2026-08-11 (Upstash "DB capacity quota exceeded" on the 1GB plan cap both environments are on) — tracked as [GitHub issue #1](https://github.com/goodgorithm/goodgorithm/issues/1). Root cause was largely a specific tradeoff: 6f6b271 (2026-08-09) restored `dedup.py`'s `NUM_PERM`/`NUM_BANDS` from a cost-optimized 64/8 back to the empirically-verified 128/16, roughly doubling per-post Redis writes, with no corresponding change to the 1GB cap — a ~3-day slide to the threshold.

- `processing/src/redis_guard.py` (new): checked once per cycle, before that cycle's dedup/bot-filter/topicality writes (`pipeline.py`'s `enforce_redis_capacity()`, called from `main.py`). Reads Redis's own `INFO memory` `used_memory` figure — there was previously zero visibility into Redis usage anywhere in the codebase — and once usage crosses 85% of `REDIS_MAX_BYTES` (config/env var, default `1073741824` = 1GB, matching both environments' current plan), proactively clears expendable data instead of writing blind until Upstash rejects a write and crashes the process. Deliberately never touches dedup's own state (`lsh:band:*`, `mh:*`, `dedup:cluster:*`) — silently losing that would let duplicate content back into the feed unnoticed, a worse failure than the loud crash this guard prevents. Only clears `burst:entity:*` (topicality's explicitly short-lived "spiking now" signal) and `cluster:*:authors` (bot-filter's secondary self-dup signal; `botvel:*` velocity tracking is untouched).
- Fixed a rolling-TTL bug present in both `dedup.py`'s `lsh:band:*` sets and `bot_filter.py`'s `cluster:{cluster_id}:authors` sets: both re-issued `EXPIRE` on every hit/new-member instead of only when first created, so a sustained duplicate/spam wave — exactly what these two modules exist to catch — could keep either key's 24h TTL rolling forward indefinitely. Now uses `EXPIRE ... NX` (only sets the TTL if the key doesn't already have one), same call count, fixed window instead of rolling.
- `dedup.py`'s `mh:{post_id}` (the largest single per-key payload, written on every processed post) now stores the MinHash signature as base64 of its raw `uint32` bytes instead of a comma-separated decimal string — ~1.3KB down to ~700 bytes, confirmed via `serialize_minhash`/`deserialize_minhash`. `deserialize_minhash` treats any old-format or incompatible-`NUM_PERM` data as "no signature" rather than raising, so the up-to-24h window of still-live old-format keys after this deploys degrades gracefully instead of crashing a cycle (same pattern `ef68f0c` established for `NUM_PERM` changes).
- `topicality.py`'s `burst:entity:*` key names are now capped at 100 chars (`ENTITY_KEY_MAX_LEN`) — entity text comes straight from spaCy NER with no prior bound, an unbounded-length key pattern.

## Monitoring & observability

Set up 2026-08-09/10, directly motivated by a silent hour-long `processing` outage that Railway's own crash alerting never caught — the restart policy kept successfully bringing the container back up every ~4 minutes, so the failure was invisible at the infra level even though `processing` was crash-looping on business logic inside an otherwise-healthy-looking container.

- **Heartbeats (Healthchecks.io)** — dead-man's-switch monitoring, 4 checks: `processing`×staging/production, `ingestion`×staging/production (deliberately 4 separate checks, not 2 shared ones — a shared check would let a healthy staging heartbeat mask a broken production one). `processing/src/heartbeat.py`'s `ping()` fires once per fully successful cycle, from the very end of `main.py`'s loop — placed after `run_cycle`, `refresh_rankings`, and `cleanup_old_data` all complete without raising, and deliberately wrapped in no try/except, since an unhandled exception crashing the process before that line *is* the missed-ping signal the monitor needs to see. `ingestion/src/heartbeat.ts` is shaped differently since ingestion is event-driven, not cyclic — it pings periodically (5 min default) but only if at least one post was actually inserted since the last check, so a quiet window with zero inserts is exactly the failure it catches. Both URLs are optional env vars (`HEARTBEAT_URL_PROCESSING`, `HEARTBEAT_URL_INGESTION`, documented in `.env.example`, set per-service per-environment in Railway) — unset means no-op, never blocks startup. The Healthchecks.io account and the 4 checks themselves are non-repo state, set up manually in their dashboard.
- **Real health check** — `api/`'s `/health` does an actual `SELECT 1` against Postgres (`api/src/db.ts`'s `checkDatabaseConnection()`), bounded to a 3s timeout via `Promise.race` so an unreachable DB fails fast instead of hanging on `postgres.js`'s ~30s default `connect_timeout`. Returns 503 `{status:"error",database:"unreachable"}` on failure, `{status:"ok"}` on success. Railway's `healthcheckPath` is set to `/health` in both `api` environments — predates this change but wasn't meaningful until now, since the old handler always returned 200 regardless of DB state.
- **External uptime checks (Better Stack)** — 4 targets, non-repo: `/health` and `web/`'s root, each on staging and production.
- **Railway Observability Dashboard** — per-environment, configured in the Railway UI, non-repo.
- **Cloudflare Workers observability** — `web/wrangler.jsonc`'s `observability.enabled: true`, free request/error analytics for the deployed Worker. This is the one piece of the above that *is* in the repo.
- **Deliberately not set up**: Railway's Pro-gated resource-threshold Monitors (the free heartbeat+uptime approach already closes the gap that mattered, at zero cost) and a public status page (planned to land alongside the Stage 4 mission page once the app is actually public, per the Pre-v1 Roadmap).

## Visual identity

Settled 2026-08-10 through 7 rounds of live iteration (Artifact-based mood boards, real component mockups in both themes — not abstract swatches). Full rationale and the concepts that got ruled out (an open-arc icon that read as a loading spinner, an uppercase-G that read as a power/off glyph, a two-g composition that was too busy) are in the Decisions Log.

**Implemented in `web/` as of 2026-08-11.** `src/theme.css` holds the palette as CSS custom properties (light values on `:root`, dark values under `prefers-color-scheme: dark` — no manual toggle exists), which every CSS Module now references instead of the hardcoded literals they used to scatter (`PostCard.module.css`, `LinkCard.module.css`, etc.). Manrope is self-hosted via `@fontsource-variable/manrope` (not a CDN call, so the woff2s get precached by the PWA's service worker like every other build asset). `Logo.tsx`/`Wordmark.tsx` render the mark/wordmark from the spec below; `App.tsx`'s header uses `Wordmark` in place of the old plain-text heading. The shipped PWA icons (`public/icons/`, favicon) were regenerated from the mark, replacing the placeholder uppercase-G monogram. **Flagged to be reviewed once more, fresh, before v1 ships** — see the Pre-v1 Roadmap's Review section; implementation doesn't resolve that flag, which is about confidence in the design itself, not whether it's wired up.

- **Palette — "Signal"**: a confident, non-pastel green. Light accent `#1F9D55`, dark accent `#3ECB79`. Dark-mode backgrounds are warm-tinted near-black (e.g. `#121815`/`#19221E`), not cold pure/blue-black — the dark theme needs to read as inviting, not an inverted afterthought.
- **Typography**: Manrope, for both display and body use, including the wordmark.
- **Mark**: a single lowercase **g**. SVG (100×100 viewBox, `stroke-width="9"`, `stroke-linecap="round"`):
  ```html
  <path d="M 66.13 44.45 A 20 20 0 1 1 66.13 27.55" fill="none" stroke="currentColor" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M 55 55 C 57 76, 34 94, 16 82" fill="none" stroke="currentColor" stroke-width="9" stroke-linecap="round"/>
  <circle cx="66.13" cy="44.45" r="6" fill="currentColor"/>
  <circle cx="66.13" cy="27.55" r="6" fill="currentColor"/>
  <circle cx="16" cy="82" r="6" fill="currentColor"/>
  ```
  Open bowl (circle with a gap, not a closed ring — echoes "open source"), a hooked descender that curls back under the bowl rather than swinging outward (an earlier straight-diagonal-plus-ball version read as a magnifying glass), attached off-center at roughly 4 o'clock rather than dead-bottom (matches how real lowercase g's link asymmetrically), plus three small nodes at the bowl's open ends and the tail terminus.
- **Wordmark**: "good" in the accent color at semibold/bold weight, "gorithm" in the body-text color at regular weight, set as one word with no space — `good` + `gorithm`.

## Data sources

Bluesky Jetstream (public WebSocket firehose, filtered to `app.bsky.feed.post` creates) and Mastodon public timelines (polling `fosstodon.org` + `hachyderm.io`, 30s interval). Both are open, unauthenticated protocols — no paid APIs, no scraping behind logins. English-only on both paths; every downstream model is English-only. This is deliberate: keeps the pipeline reproducible without special access.

## Infra (provisioned and live)

- **Cloudflare** — DNS, R2 for object storage (bucket `goodgorithm-models`: model checkpoints, datasets, transparency samples), Workers static assets for the PWA (`goodgorithm-web` — deliberately Workers over Pages, so deploys stay CI-driven like every other service rather than Pages' dashboard git-integration; account/token setup still pending, see Status above).
- **Railway** — project `goodgorithm`, three services (`goodgorithm-ingestion`, `goodgorithm-processing`, `goodgorithm-api`), each with `staging` and `production` environments.
- **Supabase** — Postgres. Production project + a `staging` branch off it. Migrations applied via `supabase/migrations/`.
- **Upstash** — serverless Redis, REST API (not raw `redis://`). Ephemeral, TTL'd state only: LSH bands + MinHash signatures (dedup), author velocity + self-dup tracking (bot filter), entity burst counters (topicality). Postgres holds every durable result; Redis is disposable.
- **GitHub** — this repo, org `goodgorithm`. Three long-lived branches (`main` → `staging` → `production`), mirroring the Railway/Supabase environment promotion flow — see Git conventions below.
- **Healthchecks.io** — dead-man's-switch heartbeat monitoring for `processing`/`ingestion`, 4 checks. See Monitoring & observability above.
- **Better Stack** — external uptime checks on `/health` and `web/`'s root, staging + production. See Monitoring & observability above.

Env var names are documented in `.env.example` at the repo root — never commit actual values. Real values live in Railway's environment variables (set separately per service, per environment) and nowhere else in this repo. Each service only needs a subset — `ingestion/` and `api/` just need `DATABASE_URL`; `processing/` additionally needs the Redis and R2 vars.

## Development

Each service is independent — install/run/test from within its own directory.

- **`ingestion/`, `api/`** (Node/TypeScript): `npm install`, `npm run dev` (watch mode via `tsx`), `npm run build` (type-check + compile), `npm test` (`api/` only, uses Node's built-in test runner).
- **`web/`** (Node/TypeScript, React + Vite): `npm install`, `npm run dev` (Vite dev server), `npm run build` (type-check + build, also generates the PWA manifest/service worker), `npm test` (Vitest), `npm run lint` (oxlint). Needs `VITE_API_BASE_URL` set (see `web/.env.example`) — points at a running `api/` instance.
- **`processing/`** (Python, managed with `uv`): `uv sync`, `uv run python src/main.py --once` (single cycle, for local testing) or without `--once` for the long-lived loop, `uv run pytest` (unit tests — many run without any real DB/Redis/R2 credentials, since `config.validate()` is only called explicitly from entrypoints, not at import time).
- **`training/sentiment_cnn.ipynb`**: not run locally — needs a GPU. Open in Colab or Kaggle. See the `release-sentiment-model` skill before touching this.

CI (`.github/workflows/ci.yml`) runs `processing`'s pytest suite, and builds/tests `ingestion`/`api`/`web`, on every push and PR to `main`/`staging`/`production`.

## Git conventions

- Commit messages: plain, descriptive. Include a `Co-Authored-By: Claude <noreply@anthropic.com>` trailer on commits produced by/with Claude (not required retroactively on the very first commit).
- Three long-lived branches, promoted in sequence: feature branches merge into `main` first; `main` promotes to `staging`; `staging` promotes to `production`. `staging` and `production` map directly to the matching Railway/Supabase environments — `main` itself isn't deployed anywhere, it's just the integration branch. CI runs tests/build on all three branches; pushes to `staging`/`production` additionally trigger a deploy to the matching Railway environment (per-service) once CI passes.

## Docs

This file is the condensed bridge for coding sessions. Full project documentation lives in Notion, not in this repo:

- **Published, public docs** ("Goodgorithm — Public Docs") — distilled, publish-safe docs meant for users/contributors: [Algorithm](https://app.notion.com/p/3b79243701a781a8997ed17609a60bc7) (step-by-step pipeline mechanics — the detailed companion to the "Architecture" section above) and [Infrastructure](https://app.notion.com/p/3b69243701a78144b4fafb22665c07b2) (hosting/tooling and why). Link new user-facing docs here, not in the internal workspace.
- **Internal workspace** ("Goodgorithm Docs") — Decisions Log (including implementation-phase decisions and known gaps), Project Research. Private, not for external sharing. Superseded planning docs (Infrastructure Plan, MVP Setup Checklist) live under "Goodgorithm Archive" — historical reference, not kept current.

If you have the Notion MCP connector available and need more context than this file provides (exact rationale for a past decision, full pricing research, etc.), check the internal workspace first.
