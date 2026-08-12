# Content policy

*Draft content for the app's public content policy (Pre-v1 Roadmap Stage 4, [issue #4](https://github.com/goodgorithm/goodgorithm/issues/4)) — what gets excluded from the feed, and why. Distinct from [`MISSION.md`](MISSION.md) (the values behind the project) and from the filter code itself (`processing/src/content_filter.py`, `processing/src/bot_filter.py`, `ingestion/src/blueskyLabels.ts`) — this is the policy a reader should be able to check the code against, not a restatement of the code. Treat as a strong draft, not locked copy.*

## What we exclude, and why

Goodgorithm surfaces public posts algorithmically, with no human reviewing every post before it's shown. That only works if we're honest about where the algorithm draws hard lines, and where it's making a best effort rather than a guarantee.

**We'd rather exclude too much than too little.** Where a stricter filter risks catching some legitimate content alongside whatever it's meant to stop, we accept that cost rather than loosen the filter to let more through. Zero inappropriate content in the feed matters more to us than reaching every possible good post. This principle came out of a real incident: an ad for an explicit novel reached the feed despite scoring as strongly positive — sentiment is not a measure of appropriateness, and it never will be. That's the gap the exclusions below exist to close.

### Explicit and adult content

Excluded, hard, before a post is ever scored or shown in the feed:

- Posts self-tagged with an unambiguous adult-content hashtag (currently just `#nsfw`).
- Posts Bluesky's own moderation service has labeled as adult content (pornography, sexual content, graphic media, or nudity).

We're deliberately narrow about which hashtags trigger this. We exclude tags that function as an unambiguous self-tagging convention for adult content — not identity or topic terms that merely correlate with it in some posts. An identity term like "lesbian" is not on this list and never will be by this logic: hard-excluding it would flag ordinary LGBTQ+ content as adult, which is a discrimination risk we're not willing to take in exchange for a small precision gain. If we get this balance wrong in either direction, that's a bug to report, not a tradeoff to relitigate quietly.

Bluesky's moderation labels can also arrive *after* a post has already been shown — their moderation service works asynchronously, independent of when a post was first posted. When that happens, we remove the post going forward, but we can't retroactively un-show it to anyone who already saw it. That's a real, accepted gap, not a hidden one: it reduces the exposure window, it doesn't guarantee zero exposure. Once a post is excluded this way, it stays excluded even if the label is later retracted — there's nothing to "undo" once it's gone.

Quoted posts get the same scrutiny as original posts, independently. A post you see quoting another post has had the quoted content run through the same checks — a quote doesn't inherit a pass just because the post quoting it passed.

### Spam, bots, and promotional content

We run a defensive-only filter that looks at posting velocity (is this account posting far more often than a person would), self-duplication (is the same account reposting near-identical content into the same cluster), and lexical spam patterns (heavy link-stuffing, hashtag-stuffing, or shouting). These combine into one score, and crossing a threshold excludes the post outright — never just a score penalty, no partial credit for "somewhat spammy." Posting velocity alone, even at its most extreme, is deliberately not enough to cross that threshold by itself — a genuinely active person posting a lot during breaking news shouldn't get caught by that signal alone. Within the lexical check specifically, one loud pattern is enough on its own — a post that's clean except for heavy link-stuffing still reads as spam, we don't let a couple of clean signals average it away.

This is honestly the least complete part of what we exclude today. Real sampling has turned up spam and bot accounts that get through the current filter — flight-tracker bots, "now playing" radio bots, counterfeit-goods and affiliate-link spam, and at least one partisan campaign-donation post that happened to match on general goodwill keywords. We're not going to claim this is solved. It's an area we expect to keep improving, and we'd rather say that plainly than imply a false sense of completeness.

### What we never use to make these calls

Consistent with the values in `MISSION.md`: none of the above ever reads likes, reposts, replies, or follower counts, and none of it runs through an LLM. The bot/spam filter is purely behavioral — how often an account posts, whether it's reposting near-duplicate content, and patterns in the text itself — not account metadata like follower or following counts. Every check here can only exclude a post, never boost it. If any of this ever looked like it was being used as a backdoor engagement signal, that would be a bug, not a feature.

## How this evolves

This isn't a fixed list. The hashtag and label sets above are meant to be extended as new unambiguous patterns show up, and the spam/bot filter is expected to get more capable over time, not to stay exactly as described here forever. If this document and the actual code ever disagree, trust the code — and tell us, because that means this page is stale.
