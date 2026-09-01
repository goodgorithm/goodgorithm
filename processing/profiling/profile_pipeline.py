"""cProfile harness for pipeline.run_cycle and pipeline.refresh_rankings.

Run from the processing/ directory:

    uv run python profiling/profile_pipeline.py                # both stages
    uv run python profiling/profile_pipeline.py --target run_cycle --iterations 5
    uv run python profiling/profile_pipeline.py --top 40 --sort tottime

Reads the same DATABASE_URL / REDIS_URL as the service (processing/.env). Point
them at a local copy or a read replica of production.

With --writes skip (the default) every Postgres-mutating db.* call is stubbed to
a no-op, so:
  * nothing is written -- safe to run against any database you can read, prod
    included;
  * every iteration re-scores the *identical* batch, so timings are comparable.
Redis writes (dedup / bot-filter / topicality state) are NOT stubbed -- that
state is ephemeral and its cost is part of what we are measuring; run against a
local Redis.

With --network skip (the default for run_cycle) the external-API stages
(quote resolution, thumbnail resolution) are stubbed -- they are wall-time,
not CPU, and their latency just adds variance to the profile. Pass
--network allow to include them.

Output per stage:
  * a warmup pass (not measured) to prime lazy model loads (spaCy, the ONNX
    sentiment / category sessions, fastText);
  * an unprofiled timing pass -> wall-clock min / mean / median per call;
  * a cProfile pass -> top functions by the chosen sort key, and a .prof dump
    under profiling/.profiles/ for snakeviz / `python -m pstats`.
"""

import argparse
import cProfile
import io
import logging
import os
import pstats
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="[profile] %(message)s")
logger = logging.getLogger("profile")

OUTDIR = Path(__file__).resolve().parent / ".profiles"


def _stub_db_writes(db) -> None:
    """No-op every Postgres-mutating entry point run_cycle / refresh_rankings
    can reach. Reads are left intact."""
    db.upsert_processed_posts = lambda rows: None
    db.update_rank_scores = lambda updates: None
    db.delete_raw_post = lambda post_id: False
    db.delete_old_raw_posts = lambda cutoff: 0


def _stub_network(quote_resolver, thumbnail_resolver) -> None:
    """Skip the two external-API stages inside run_cycle. The pure
    extract_* helpers that feed them stay in place."""
    quote_resolver.resolve_quotes = lambda uris, terms, domains: {}
    thumbnail_resolver.resolve_thumbnails = lambda urls: {}


def _run(label: str, fn, warmup: int, iterations: int, sort: str, top: int) -> None:
    print(f"\n{'=' * 72}\n{label}\n{'=' * 72}")

    for _ in range(warmup):
        fn()

    wall = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        wall.append(time.perf_counter() - t0)
    print(
        f"wall-clock over {iterations} call(s): "
        f"min {min(wall):.3f}s  mean {statistics.mean(wall):.3f}s  "
        f"median {statistics.median(wall):.3f}s"
    )

    prof = cProfile.Profile()
    for _ in range(iterations):
        prof.enable()
        fn()
        prof.disable()

    buf = io.StringIO()
    stats = pstats.Stats(prof, stream=buf).strip_dirs().sort_stats(sort)
    stats.print_stats(top)
    print(f"\ntop {top} functions by {sort} (summed over {iterations} profiled call(s)):\n")
    print(buf.getvalue())

    OUTDIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = OUTDIR / f"{label.split()[0]}-{stamp}.prof"
    prof.dump_stats(str(out))
    print(f"wrote {out}")
    print(f"  inspect: uv run python -m pstats {out}")
    print(f"  or:      uvx snakeviz {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--target",
        choices=("run_cycle", "refresh_rankings", "both"),
        default="both",
    )
    parser.add_argument("--iterations", type=int, default=3, help="profiled + timed calls per stage (default 3)")
    parser.add_argument("--warmup", type=int, default=1, help="unmeasured priming calls per stage (default 1)")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("PROCESSING_BATCH_SIZE", 500)),
        help="run_cycle batch size (default: PROCESSING_BATCH_SIZE or 500)",
    )
    parser.add_argument("--top", type=int, default=30, help="functions to print (default 30)")
    parser.add_argument(
        "--sort",
        default="cumulative",
        help="pstats sort key: cumulative, tottime, ncalls, ... (default cumulative)",
    )
    parser.add_argument(
        "--writes",
        choices=("skip", "allow"),
        default="skip",
        help="skip (default): stub Postgres writes. allow: real writes -- use a disposable DB only",
    )
    parser.add_argument(
        "--network",
        choices=("skip", "allow"),
        default="skip",
        help="skip (default): stub quote/thumbnail resolution in run_cycle. allow: hit the real APIs",
    )
    args = parser.parse_args()

    config.validate()

    import pipeline
    from infra import db
    from pipeline_stages import quote_resolver, thumbnail_resolver

    if args.writes == "skip":
        _stub_db_writes(db)
        logger.info("Postgres writes STUBBED (--writes skip) -- no rows will be mutated")
    else:
        logger.warning(
            "Postgres writes LIVE (--writes allow) -- mutating %s. Iterations drain real posts.",
            (config.DATABASE_URL or "").split("@")[-1] or "the configured database",
        )

    if args.network == "skip":
        _stub_network(quote_resolver, thumbnail_resolver)
        logger.info("external-API stages STUBBED (--network skip)")
    else:
        logger.info("external-API stages LIVE (--network allow)")

    targets = ("run_cycle", "refresh_rankings") if args.target == "both" else (args.target,)
    try:
        for name in targets:
            if name == "run_cycle":
                _run(
                    f"run_cycle  (batch_size={args.batch_size})",
                    lambda: pipeline.run_cycle(args.batch_size),
                    args.warmup,
                    args.iterations,
                    args.sort,
                    args.top,
                )
            else:
                _run(
                    "refresh_rankings",
                    pipeline.refresh_rankings,
                    args.warmup,
                    args.iterations,
                    args.sort,
                    args.top,
                )
    finally:
        db.close()


if __name__ == "__main__":
    main()
