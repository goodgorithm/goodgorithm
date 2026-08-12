# Agent instructions

This project's full agent-facing context — architecture, the load-bearing constraints, data flow, per-service dev commands, git conventions, everything — lives in [`CLAUDE.md`](CLAUDE.md), not here.

If your tool only reads `AGENTS.md`, treat this file as a redirect: **open and read `CLAUDE.md` before doing any work in this repo.** It is kept current; duplicating its content here would just give it a second copy to drift out of sync with, which is exactly what this repo's other docs (`CONTRIBUTING.md`, `MISSION.md`) already deliberately avoid doing to each other.

The one thing worth stating here directly, since it governs how contributions get judged regardless of which tool is reading this: **[`MISSION.md`](MISSION.md)'s three constraints — no LLM in the algorithm, no engagement signals in ranking, no attention-optimization in the product — are non-negotiable review criteria, not aspirational text.** Check any change against them before proposing it.
