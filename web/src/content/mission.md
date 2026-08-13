# Our mission

## It's not the humans. It's the algorithm.

Good news isn't rare. Kindness, discovery, recovery, craft, community — it's being posted right now, on the same platforms as everything else. It doesn't reach you because the algorithms deciding what you see aren't optimizing for it. They're optimizing for what keeps you scrolling, and outrage keeps you scrolling better than a story about a stranger returning a lost wallet.

So we didn't go build a curated publication. We built an algorithm — the same basic kind of system that's usually working against you, pointed at a different goal. Goodgorithm reads the same open, public feeds everyone else does ([Bluesky](https://bsky.app), [Mastodon](https://joinmastodon.org)) and surfaces what's already there, scored for genuine positivity and topical substance instead of for what keeps you hooked.

We see human-curated good-news outlets — [Good News Network](https://goodnewsnetwork.org), [Positive News](https://positive.news), and others like them — as doing the same work from a different angle, not as competitors. Editorial judgment and algorithmic filtering both have something to offer here, and we'd rather this space have more of both than either one "winning."

And we're explicit about what we're *not* trying to do: hold your attention. We're not neutral about engagement — we're actively fine with this app not being sticky. The point was never screen time. It's whatever you do after you put your phone down.

## How we decide

Three things are non-negotiable in how this gets built. Not preferences — constraints. Every feature decision gets checked against them:

- **No LLM in the algorithm itself.** What gets selected and how it's ranked runs on classic, auditable machine learning — not a large language model. We want you to be able to trust *why* a post got picked, and that means the decision logic has to be something that can actually be inspected, published, and reasoned about end to end, without drift or hallucination in the loop. (We do use LLM tools, including Claude, openly to help build and maintain the project — this constraint is about what powers the algorithm, not about how the codebase gets written.)
- **No engagement signals in ranking.** We never read likes, reposts, replies, or follower counts from the platforms we pull from, anywhere in scoring or ranking. That's not a tuning choice we might revisit — it's the one thing that would quietly turn this back into exactly the kind of algorithm we built this to counter.
- **No attention-optimization in the product.** No streaks. No "come back" notifications. No autoplay-next. Nothing engineered to maximize time in the app. If a feature's real purpose is to make this harder to put down, it doesn't ship, regardless of how it's framed.

## What we're committing to

- **Free and ad-free, forever.** No paywall, no premium tier, no ads. If this project needs support to keep running, that support is voluntary and community-driven — never funded by selling access to you or your data.
- We can back that with more than a promise: our API has no accounts, no login, and holds no user data by design. There's nothing to sell even if we ever wanted to. The architecture makes the commitment true, not just stated.
- **Open by default.** The code, the model weights, and the training data behind the algorithm are all published. If you don't trust what we're saying about how a post got selected, you don't have to — you can go look.

## Join us

The codebase is public and MIT-licensed today, but honestly: we're not yet set up to take outside contributions well, and we'd rather say that plainly than pretend otherwise. When that opens up, here's what to expect.

We're looking for people who actually want the three principles above to hold, not just tolerate them — they're the review bar for anything that gets merged, not a mission statement that stops applying once you're looking at a pull request. If a contribution technically works but leans even a little toward re-engagement mechanics or opaque scoring, it's not going in, and we'd rather tell you that up front than after you've built it.

One more thing worth being upfront about, in the same spirit as the transparency we're asking of the algorithm itself: a meaningful share of this codebase has been built with AI pair-programming (Claude Code), openly and on purpose. We think that's consistent with everything above, not in tension with it — but you should know it going in.

If that sounds like your kind of project, we're glad you're here. Watch this space for how to get involved.
