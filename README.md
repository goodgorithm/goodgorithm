# Goodgorithm

An open-source algorithmic feed of positive/uplifting public social posts, curated by classic, tried-and-tested ML — built to counter the negativity bias of mainstream platform algorithms.

**Status:** early development. Ingestion, the scoring/ranking pipeline, and a read-only feed API are built, tested, and deployed to staging and production. A PWA frontend (`web/`) is built and passing CI, but not deployed yet — pending one-time Cloudflare Workers account setup.

## What this is

- Aggregates public posts from open, free protocols (Bluesky Jetstream, Mastodon public timelines) — no paid APIs, no scraping behind logins.
- Scores and ranks with classical ML — MinHash/LSH dedup, a small CNN for sentiment, TF-IDF + spaCy NER for topicality, MMR for diversity — not an LLM. See [A note on LLMs](#a-note-on-llms).
- Never reads likes, reposts, replies, or follower counts from the source platform anywhere in scoring or ranking. A deliberate, load-bearing constraint, not an aspiration.
- Free forever, no ads, no revenue on the core product.

For the full step-by-step walkthrough of how a post moves from ingestion to the ranked feed, see the published [Algorithm](https://app.notion.com/p/3b79243701a781a8997ed17609a60bc7) doc.

## Services

| Path | Language | What it does |
|---|---|---|
| `ingestion/` | TypeScript | Long-lived process consuming Bluesky Jetstream + polling Mastodon, writes raw posts to Postgres. |
| `processing/` | Python | Dedup, bot filter, topicality, sentiment, ranking — the actual algorithm. |
| `api/` | TypeScript (Fastify) | Read-only `/feed` and `/health` endpoints. |
| `web/` | TypeScript (React + Vite) | PWA frontend — infinite-scroll feed, deployed as static assets on Cloudflare Workers. |
| `training/` | Python (notebook) | Sentiment CNN training, run manually on Colab/Kaggle, plus model-release tooling. |
| `supabase/migrations/` | SQL | Postgres schema. |

Each service has its own `package.json` / `pyproject.toml` and expects its own `.env` — see `.env.example` in the repo root for the full list of variables and which services need which.

## Docs

Full project context for anyone (human or Claude) picking this up lives in [`CLAUDE.md`](CLAUDE.md), not scattered across this README. Deeper docs live in Notion:

- **Published, public docs:** [Goodgorithm — Public Docs](https://app.notion.com/p/3b69243701a7813bbf0feabdcec0a7b0) — start with **Algorithm** (step-by-step pipeline walkthrough) and **Infrastructure** (hosting/tooling and why).
- **Internal docs** (decisions log, research, infra planning with pricing, setup checklist): team Notion workspace, not public.

## A note on LLMs

The content-selection pipeline itself — sentiment scoring, topic/newsworthiness detection, ranking — runs on classic, well-understood ML: TF-IDF, named entity recognition, small CNNs over word embeddings. Not a large language model.

That's a fit-for-purpose choice, not a blanket stance against LLMs. The whole premise of this project is that people can trust *why* a post got selected. Classical ML gives us models that are small, auditable, and predictable in ways LLMs generally aren't today — the training data and decision logic can be published and inspected end to end, and behavior doesn't drift or hallucinate the way a less constrained model can. For a feed whose entire pitch is "trust the selection," that predictability matters more to us than the extra flexibility an LLM could offer elsewhere in the pipeline.

This is specifically about what powers the algorithm — it doesn't extend to how the project itself gets built. We're open about using LLM-based tools (including Claude) for development, research, and docs. "No LLMs in the filter," not "no LLMs anywhere."

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Not yet open for outside contributions — still early and moving fast. Issues/discussions welcome.
