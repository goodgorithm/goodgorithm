# profiling/

`profile_pipeline.py` — a cProfile harness for the two CPU-heavy pipeline
stages, `pipeline.run_cycle` and `pipeline.refresh_rankings`. Use it to get a
function-level breakdown of where a cycle spends its time before changing any
scoring code.

## Run

From `processing/`:

```
uv run python profiling/profile_pipeline.py                      # both stages, defaults
uv run python profiling/profile_pipeline.py --target run_cycle --iterations 5
uv run python profiling/profile_pipeline.py --target refresh_rankings --sort tottime --top 40
```

It reads `DATABASE_URL` / `REDIS_URL` from `processing/.env`, same as the
service. The database must be migration-current (`supabase/migrations/`) and
hold real rows — an empty or stale schema will error out in the first stage.

## What the defaults do

- `--writes skip` — every Postgres-mutating `db.*` call is stubbed to a no-op.
  Nothing is written, so it is safe against any database you can read
  (production included), and every iteration re-scores the **identical** batch,
  making timings comparable. Use `--writes allow` only against a disposable
  copy; there, each iteration drains real unprocessed rows.
- `--network skip` — the external-API stages in `run_cycle` (Bluesky quote
  resolution, thumbnail resolution) are stubbed. They are wall-time, not CPU,
  and add variance. `--network allow` includes them.
- Redis writes (dedup / bot-filter / topicality state) are **not** stubbed —
  that state is ephemeral and its cost is part of what we are measuring. Run
  against a local Redis.

## Output

Per stage: a warmup pass (primes lazy model loads — spaCy, the ONNX
sentiment/category sessions, fastText), an unprofiled wall-clock pass
(min / mean / median per call), then a cProfile pass printing the top functions
by the chosen `--sort` key.

Each run also drops a `.prof` file in `profiling/.profiles/` (git-ignored):

```
uv run python -m pstats profiling/.profiles/run_cycle-<stamp>.prof
uvx snakeviz profiling/.profiles/run_cycle-<stamp>.prof
```
