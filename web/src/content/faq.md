# FAQ

## What is Goodgorithm?

An algorithmic feed of positive, uplifting public posts from [Bluesky](https://bsky.app) and [Mastodon](https://joinmastodon.org). Nothing is written or curated by a person — an algorithm reads the same open, public feeds everyone else does and ranks what's already there for genuine positivity and topical substance, instead of for what keeps you scrolling. See the [Mission](https://github.com/goodgorithm/goodgorithm/wiki/Mission) wiki page for the full reasoning.

## Why "algorithm"? Isn't that the thing that's usually the problem?

That's the point. Mainstream feed algorithms aren't neutral — they're tuned to maximize how long you stay. Goodgorithm is the same basic kind of system, pointed at a different goal, and built openly enough that you can actually check *why* something got picked instead of taking our word for it.

## Does an AI/LLM decide what shows up in my feed?

No. Content selection — sentiment scoring, topic detection, ranking — runs on classical, auditable machine learning (TF-IDF, named-entity recognition, a small trained neural network for sentiment), not a large language model. That's a deliberate, non-negotiable constraint: an LLM can drift or hallucinate in ways that would undermine the whole "trust why a post got selected" premise. (LLM tools, including Claude, are used openly to help *build* the project — that's a separate question from what powers the algorithm itself.) Full mechanics: [Algorithm](https://github.com/goodgorithm/goodgorithm/wiki/Algorithm).

## Does it use likes, reposts, or follower counts to rank posts?

Never. No engagement metric from the source platform factors into scoring or ranking, anywhere. Ranking runs purely on a post's own content: sentiment, topicality, and recency.

## Is it free?

Yes, and it always will be — no paywall, no premium tier, no ads. If the project ever needs financial support to keep running, that support is voluntary, not funded by selling access to you or your data. There's no login and no user data collected, so there's nothing to sell even if that ever changed.

## What does it exclude from the feed?

Explicit/adult content, spam and bot accounts, and non-English posts (every model in the pipeline is English-only). The full policy — including where the filters are still imperfect, and how to report something that slipped through — is on the [Content Policy](https://github.com/goodgorithm/goodgorithm/wiki/Content-Policy) wiki page.

## I saw something inappropriate in the feed. What do I do?

[Open a moderation report](https://github.com/goodgorithm/goodgorithm/issues/new?template=moderation_report.md) on GitHub. Reports are what feed the manual blocklist described in the content policy — this is genuinely how bad actors get caught, not a formality.

## Is the code open source?

Yes, MIT-licensed, on [GitHub](https://github.com/goodgorithm/goodgorithm) — including the model weights and training data behind the algorithm, not just the app code.

## Where did the "Our mission" and "The algorithm" pages go?

They moved to the [GitHub Wiki](https://github.com/goodgorithm/goodgorithm/wiki), along with the content policy and an infrastructure overview, so the app itself stays focused on the feed. Nothing was removed — it's all still public, just not sitting in the app's own navigation.

## Can I use this on my phone?

The web app is a PWA — on most browsers you can "Add to Home Screen" for an app-like experience. Native iOS/Android builds exist in the codebase; whether they're published to the App Store/Play Store yet is tracked on GitHub.

## Can I contribute?

The project isn't yet set up to take outside contributions smoothly, and we'd rather say that plainly than pretend otherwise. Watch the [GitHub repo](https://github.com/goodgorithm/goodgorithm) for when that opens up — the [Mission](https://github.com/goodgorithm/goodgorithm/wiki/Mission) page has more on what we'll be looking for.
