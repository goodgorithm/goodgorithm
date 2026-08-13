# The algorithm

This walks through exactly what happens to a post between the moment it's ingested and the moment it might appear in the ranked feed — every stage, every threshold, in the order they actually run. It's the mechanism behind the "no engagement signals, no LLM" claims on the [mission page](/mission).

**Ingestion → Dedup → Bot filter → Topicality → Sentiment → Base score → Ranking (MMR) → API**

## 1. Ingestion

Two independent, always-on consumers write into a single `raw_posts` table, each post keyed by `(source, source_id)` so re-ingesting the same post is a no-op rather than a duplicate row.

**Bluesky** — a persistent WebSocket connection to the public Jetstream firehose, subscribed specifically to `app.bsky.feed.post` creation events. Reconnects with exponential backoff (5s → 60s cap) on any drop. Only posts with no language tag or an explicit `en` tag are kept.

**Mastodon** — polls the public timelines of two instances (`fosstodon.org`, `hachyderm.io`) every 30 seconds. Only `public`-visibility, English posts are kept; HTML is stripped to plain text. Accounts that have opted out of discovery or search-engine indexing (the `discoverable`/`indexable` account fields) are skipped — public visibility isn't the same thing as consent for reuse.

Neither path touches an authenticated endpoint or a paid API.

## 2. Deduplication

Runs first in the processing cycle, since later stages need to know which posts are near-duplicates of each other.

Text is normalized (lowercased, URLs and @mentions stripped), broken into overlapping 4-word shingles, and hashed into a 128-permutation MinHash signature. The signature is banded into 16 LSH bands and checked against Redis for candidate matches from other recently-seen posts. A candidate is confirmed using the full MinHash Jaccard similarity — 0.7 or above counts as a near-duplicate.

The first post seen for a cluster is canonical; later near-duplicates join the same cluster as non-canonical. Only canonical posts are eligible for ranking. Redis state has a 24-hour TTL — a fixed window, not one that resets on every hit.

## 3. Bot filter

Defensive-only: this stage can exclude a post from ranking, but never boost one. Three purely content- and behavior-derived signals — nothing here reads likes, follows, or reposts:

- **Posting velocity** — posts in the last hour, capped at 15/hour for scoring.
- **Self-duplication** — has this author already posted into this exact dedup cluster before?
- **Lexical spam patterns** — link density, hashtag density, and ALL-CAPS ratio, each capped independently; the *worst* of the three counts, not the average.

These combine into a weighted score — velocity 40%, self-duplication 35%, lexical 25% — and 0.5 or above flags a post as bot-like, excluding it from ranking. Velocity alone, even maxed out, can never cross that threshold by itself — a genuinely active person during breaking news shouldn't get flagged from that signal alone.

## 4. Topicality

Combines two signals:

**TF-IDF salience** — within each processing batch, a post is scored by the mean weight of its top 3 TF-IDF terms, so it's judged by its most distinctive words, not diluted by length.

**Entity burst** — [spaCy](https://spacy.io)'s named-entity recognizer extracts people, organizations, places, events, and similar entities. Each mention bumps a short-lived (3-hour) Redis counter per entity across the whole incoming stream. A post mentioning an entity currently spiking (up to 5 mentions in that window) gets its topicality score boosted, up to double.

## 5. Sentiment

A small convolutional neural network ([Kim 2014](https://arxiv.org/abs/1408.5882)-style: parallel convolutions over word embeddings, global max-pooling, dropout, a linear 3-way classifier), trained on three public sentiment datasets — [Sentiment140](https://help.sentiment140.com/for-students), [TweetEval](https://github.com/cardiffnlp/tweeteval)/[SemEval-2017](https://aclanthology.org/S17-2088/), and [GoEmotions](https://arxiv.org/abs/2005.00547) — harmonized into one negative/neutral/positive scheme — and exported to ONNX for lightweight, GPU-free inference.

Output is a single score from -1 to 1. If no trained model can be loaded, the pipeline falls back automatically to [VADER](https://ojs.aaai.org/index.php/ICWSM/article/view/14550), a rule-based sentiment lexicon — which scorer produced a given score is recorded alongside it, never hidden after the fact.

## 6. Base score

Every post gets a single content-derived base score:

```
base_score = positivity(sentiment) × topicality × recency_decay
```

`positivity` is the sentiment score floored at zero. `recency_decay` halves every 12 hours and is a pure function of post age. There is no field anywhere in this computation that could carry a like, repost, or follower count, even accidentally.

## 7. Ranking (MMR)

Every processing cycle, the eligible pool is re-ranked from scratch. Eligible means: not bot-flagged, dedup-canonical, and sentiment score at or above 0.3. The pool is windowed to the last 72 hours — bounded tighter in practice by the current 24-hour data retention — and capped at the top 2,000 posts by base score if it's larger than that, so ranking stays computationally bounded.

Ranking uses [Maximal Marginal Relevance (MMR)](https://doi.org/10.1145/290941.291025): it greedily builds the ranked list one post at a time, picking whichever remaining post maximizes `0.7 × base_score − 0.3 × (similarity to posts already selected)`. Similarity blends TF-IDF cosine similarity and shared-entity overlap, weighted equally. This is what stops one big story from filling the feed with near-identical posts.

## 8. Serving

The API is stateless, read-only, and unauthenticated — no login, nothing user-specific about the response. The feed is paginated with an opaque cursor so results stay stable as new posts get scored between requests. Every post includes its full component scores, not just its final position.

## Model training and publishing

The sentiment CNN is trained separately from the always-on pipeline — periodically, by a human, on a free Colab or Kaggle GPU — then published as an immutable, versioned artifact alongside audit metadata (dataset composition, evaluation metrics, the exact commit it was trained against). Promoting a version to "live" is a separate, deliberately-gated step from publishing it.

Every time a version is promoted to production, its weights are also mirrored to a public GitHub Release, so the exact model running in production is genuinely downloadable by anyone — not just claimed to be open.

## Data retention

For now, both Postgres and Redis only keep the last 24 hours of posts and pipeline state — an alpha-stage decision to limit storage growth. This window is expected to grow post-alpha.

## What's deliberately excluded

- **No account-level engagement metrics** — likes, reposts, replies, follower counts — anywhere in scoring or ranking.
- **No LLM anywhere in this pipeline.** Every stage above is classical ML/NLP.
- **No personalization.** Everyone sees the same ranked feed.

See the [mission page](/mission) for why these are non-negotiable, not just current defaults.

## Caveats

This is a young, actively-changing pipeline — thresholds and weights may shift as real data comes in. The full source code is public if you want the exact current numbers.
