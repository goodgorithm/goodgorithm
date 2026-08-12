# The algorithm

*Draft content for the app's public Algorithm page (Pre-v1 Roadmap Stage 4, [issue #10](https://github.com/goodgorithm/goodgorithm/issues/10)). Adapted from an earlier internal draft, but every number below was re-checked directly against the current code while writing this — not copied uncritically, since the earlier draft turned out to already be stale in places (e.g. it described dedup as 64-permutation/8-band; the code has run 128-permutation/16-band since before that draft's own cited snapshot). Code is the real source of truth: if this page and the code ever disagree, trust the code, and treat that as a bug in this page.*

This walks through exactly what happens to a post between the moment it's ingested and the moment it might appear in the ranked feed — every stage, every threshold, in the order they actually run. It's the mechanism behind the "no engagement signals, no LLM" claims in [`MISSION.md`](MISSION.md).

**Ingestion → Dedup → Bot filter → Topicality → Sentiment → Base score → Ranking (MMR) → API**

## 1. Ingestion

Two independent, always-on consumers write into a single `raw_posts` table, each post keyed by `(source, source_id)` so re-ingesting the same post is a no-op rather than a duplicate row.

**Bluesky** — a persistent WebSocket connection to the public Jetstream firehose, subscribed specifically to `app.bsky.feed.post` creation events. Reconnects with exponential backoff (5s → 60s cap) on any drop. Only posts with no language tag or an explicit `en` tag are kept.

**Mastodon** — polls the public timelines of two instances (`fosstodon.org`, `hachyderm.io`) every 30 seconds. Only `public`-visibility, English posts are kept; HTML is stripped to plain text.

Neither path touches an authenticated endpoint or a paid API.

[`ingestion/src/bluesky.ts`](https://github.com/goodgorithm/goodgorithm/blob/main/ingestion/src/bluesky.ts) · [`ingestion/src/mastodon.ts`](https://github.com/goodgorithm/goodgorithm/blob/main/ingestion/src/mastodon.ts)

## 2. Deduplication

Runs first in the processing cycle, since later stages need to know which posts are near-duplicates of each other.

Text is normalized (lowercased, URLs and @mentions stripped), broken into overlapping 4-word shingles, and hashed into a 128-permutation MinHash signature. The signature is banded into 16 LSH bands and checked against Redis for candidate matches from other recently-seen posts. A candidate is confirmed using the full MinHash Jaccard similarity — 0.7 or above counts as a near-duplicate.

The first post seen for a cluster is canonical; later near-duplicates join the same cluster as non-canonical. Only canonical posts are eligible for ranking. Redis state (LSH bands, signatures, cluster lookups) has a 24-hour TTL — a fixed window, not one that resets on every hit, so a heavily-duplicated post can't keep its Redis footprint alive indefinitely.

[`processing/src/dedup.py`](https://github.com/goodgorithm/goodgorithm/blob/main/processing/src/dedup.py)

## 3. Bot filter

Defensive-only: this stage can exclude a post from ranking, but never boost one. Three purely content- and behavior-derived signals — nothing here reads likes, follows, or reposts:

- **Posting velocity** — posts in the last hour, capped at 15/hour for scoring.
- **Self-duplication** — has this author already posted into this exact dedup cluster before?
- **Lexical spam patterns** — link density, hashtag density, and ALL-CAPS ratio, each capped independently; the *worst* of the three counts, not the average.

These combine into a weighted score — velocity 40%, self-duplication 35%, lexical 25% — and 0.5 or above flags a post as bot-like, excluding it from ranking. Velocity alone, even maxed out, can never cross that threshold by itself (its 40% weight tops out below 0.5) — a genuinely active person during breaking news shouldn't get flagged from that signal alone.

[`processing/src/bot_filter.py`](https://github.com/goodgorithm/goodgorithm/blob/main/processing/src/bot_filter.py) — see also [`CONTENT_POLICY.md`](CONTENT_POLICY.md) for known gaps in what this currently catches.

## 4. Topicality

Combines two signals:

**TF-IDF salience** — within each processing batch, a post is scored by the mean weight of its top 3 TF-IDF terms, so it's judged by its most distinctive words, not diluted by length.

**Entity burst** — spaCy's named-entity recognizer extracts people, organizations, places, events, and similar entities (excluding dates, numbers, money as noise). Each mention bumps a short-lived (3-hour) Redis counter per entity across the whole incoming stream, not just this batch. A post mentioning an entity currently spiking (up to 5 mentions in that window) gets its topicality score boosted, up to double.

[`processing/src/topicality.py`](https://github.com/goodgorithm/goodgorithm/blob/main/processing/src/topicality.py)

## 5. Sentiment

A small convolutional neural network (Kim 2014-style: parallel convolutions over word embeddings at 3/4/5-word windows, global max-pooling, dropout, a linear 3-way classifier), trained on three public sentiment datasets — Sentiment140, TweetEval/SemEval-2017, and GoEmotions, harmonized into one negative/neutral/positive scheme — and exported to ONNX for lightweight, GPU-free inference.

Output is `P(positive) − P(negative)`, a single score from -1 to 1.

If no trained model can be loaded (object storage unreachable, or nothing published yet), the pipeline falls back automatically to VADER, a rule-based sentiment lexicon. Which scorer actually produced a given post's score is recorded alongside it (`sentiment_method`), never hidden after the fact.

[`processing/src/sentiment.py`](https://github.com/goodgorithm/goodgorithm/blob/main/processing/src/sentiment.py) · [`processing/src/sentiment_model.py`](https://github.com/goodgorithm/goodgorithm/blob/main/processing/src/sentiment_model.py)

## 6. Base score

Every post gets a single content-derived `base_score`:

```
base_score = positivity(sentiment) × topicality × recency_decay
```

`positivity` is the sentiment score floored at zero — only posts that read as positive contribute at all. `recency_decay` halves every 12 hours and is a pure function of post age — nothing else. There is no field anywhere in this computation that could carry a like, repost, or follower count, even accidentally.

[`processing/src/ranking.py`](https://github.com/goodgorithm/goodgorithm/blob/main/processing/src/ranking.py) (`compute_base_score`)

## 7. Ranking (MMR)

Every processing cycle, the eligible pool is re-ranked from scratch. Eligible means: not bot-flagged, dedup-canonical, and sentiment score at or above 0.3. The pool is windowed to the last 72 hours — bounded tighter in practice by the current 24-hour data retention (see below) — and additionally capped at the top 2,000 posts by `base_score` if it's larger than that, so the ranking pass stays computationally bounded rather than growing unboundedly with ingestion volume. That cap is self-correcting: it's reselected fresh every cycle, so a post that misses the cut can still enter later as higher-scoring posts age out.

Ranking uses Maximal Marginal Relevance (MMR): it greedily builds the ranked list one post at a time, at each step picking whichever remaining post maximizes `0.7 × base_score − 0.3 × (similarity to posts already selected)`. Similarity blends TF-IDF cosine similarity and shared-entity overlap, weighted equally. This is what stops one big story from filling the feed with near-identical posts. A post's position in this selection order becomes its `rank_score`.

[`processing/src/ranking.py`](https://github.com/goodgorithm/goodgorithm/blob/main/processing/src/ranking.py) (`rank_posts`)

## 8. Serving

The API is stateless, read-only, and unauthenticated — no login, nothing user-specific about the response. `/feed` returns posts ordered by `rank_score`, paginated with an opaque cursor so results stay stable as new posts get scored in the background between requests. Every post includes its full component scores — sentiment, topicality, base, rank — and extracted entities, not just its final position.

[`api/src/routes/feed.ts`](https://github.com/goodgorithm/goodgorithm/blob/main/api/src/routes/feed.ts)

## Model training and publishing

The sentiment CNN is trained separately from the always-on pipeline — periodically, by a human, on a free Colab or Kaggle GPU. The training notebook loads and harmonizes the three public datasets above, trains the model, evaluates it against a held-out split and TweetEval's own independent test set, exports it to ONNX, and publishes it — as an immutable, versioned artifact, alongside audit metadata (dataset composition counts, evaluation metrics, the exact code commit it was trained against) — to Cloudflare R2. Promoting a version to "live" is a separate, deliberately-gated step from publishing it, so a training run never silently changes what's in production.

**On making this actually open, not just claimed:** the R2 bucket the pipeline reads from is private — that's an operational store, not a public distribution channel, and was never meant to be one. Every time a model version is promoted to production, its three artifacts (`model.onnx`, `vocab.json`, `config.json`) are also mirrored to a public GitHub Release on this repo, tagged `sentiment-cnn-<version>`, so the exact weights running in production are genuinely downloadable by anyone — not just claimed to be open. Note the harmonized training *text* itself isn't republished (only its composition — counts per source dataset); the underlying datasets (Sentiment140, TweetEval, GoEmotions) are each already independently public and cited by name above.

[`training/sentiment_cnn.ipynb`](https://github.com/goodgorithm/goodgorithm/blob/main/training/sentiment_cnn.ipynb) · [`training/r2_release.py`](https://github.com/goodgorithm/goodgorithm/blob/main/training/r2_release.py) · [releases tagged `sentiment-cnn-*`](https://github.com/goodgorithm/goodgorithm/releases)

## Data retention

For now, both Postgres and Redis only keep the last 24 hours of posts and pipeline state — an alpha-stage decision to limit storage growth, not a reflection of how far back the feed's judgment reaches. This window is expected to grow post-alpha.

## What's deliberately excluded

- **No account-level engagement metrics** — likes, reposts, replies, follower counts — anywhere in scoring or ranking. Not down-weighted, not absent by convention: the data model for ranking has no field that could hold them.
- **No LLM anywhere in this pipeline.** Every stage above is classical ML/NLP — TF-IDF, MinHash, a small CNN, rule-based fallbacks.
- **No personalization.** Everyone sees the same ranked feed. There's no login or per-user state.

See [`MISSION.md`](MISSION.md) for why these are non-negotiable, not just current defaults.

## Caveats

This is a young, actively-changing pipeline — thresholds and weights may shift as real data comes in. If you're relying on a specific number or behavior described above, check the linked source file first; it's the actual source of truth, this page is a description of it.
