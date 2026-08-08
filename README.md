# Goodgorithm

An open-source algorithmic feed of positive/uplifting public social posts, curated by classic, tried-and-tested ML — built to counter the negativity bias of mainstream platform algorithms.

**Status:** pre-alpha, pipeline design in progress. Nothing runnable yet.

## What this is

- Aggregates public posts from open, free protocols (Bluesky Jetstream, Mastodon public timelines) — no paid APIs, no scraping behind logins.
- Classifies positivity/newsworthiness with classical ML and small neural models (CNN sentiment, TF-IDF + NER for topicality) — well-understood techniques, not keyword lexicons alone, and not an LLM. See [A note on LLMs](#a-note-on-llms) below for why.
- Ranks and dedupes without ever reading likes, reposts, replies, or follower counts from the source platform. That's a deliberate, load-bearing design constraint, not an aspiration — see the Decisions Log for what got caught and fixed when an early ranking draft violated it.
- Free forever, no ads, no revenue on the core product.

## Docs

Project docs (decisions log, algorithm research, naming/legal notes) live in the team's Notion workspace, not in this repo. This README and in-repo `docs/` (as code lands) cover setup and architecture specifics only.

## A note on LLMs

The content-selection pipeline itself — sentiment scoring, topic/newsworthiness detection, ranking — runs on classic, well-understood ML: TF-IDF, named entity recognition, small CNNs over word embeddings. Not a large language model.

That's a fit-for-purpose choice, not a blanket stance against LLMs. The whole premise of this project is that people can trust *why* a post got selected. Classical ML gives us models that are small, auditable, and predictable in ways LLMs generally aren't today — the training data and decision logic can be published and inspected end to end, and behavior doesn't drift or hallucinate the way a less constrained model can. For a feed whose entire pitch is "trust the selection," that predictability matters more to us than the extra flexibility an LLM could offer elsewhere in the pipeline.

This is specifically about what powers the algorithm — it doesn't extend to how the project itself gets built. We're open about using LLM-based tools (including Claude) for development, research, and docs. "No LLMs in the filter," not "no LLMs anywhere."

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Not yet open for contributions — pipeline architecture is still being scoped. Issues/discussions welcome once there's code to react to.
