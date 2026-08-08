# Goodgorithm

An open-source, non-LLM algorithmic feed of positive/uplifting public social posts — built to counter the negativity bias of mainstream platform algorithms.

**Status:** pre-alpha, pipeline design in progress. Nothing runnable yet.

## What this is

- Aggregates public posts from open, free protocols (Bluesky Jetstream, Mastodon public timelines) — no paid APIs, no scraping behind logins.
- Classifies positivity/newsworthiness with classical ML and small neural models (CNN sentiment, TF-IDF + NER for topicality) — not an LLM, and not just keyword lexicons.
- Ranks and dedupes without ever reading likes, reposts, replies, or follower counts from the source platform. That's a deliberate, load-bearing design constraint, not an aspiration — see the Decisions Log for what got caught and fixed when an early ranking draft violated it.
- Free forever, no ads, no revenue on the core product.

## Docs

Project docs (decisions log, algorithm research, naming/legal notes) live in the team's Notion workspace, not in this repo. This README and in-repo `docs/` (as code lands) cover setup and architecture specifics only.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Not yet open for contributions — pipeline architecture is still being scoped. Issues/discussions welcome once there's code to react to.
