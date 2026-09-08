# Updates

Milestones and notable changes to Goodgorithm, newest first. Nothing to sign up for:
bookmark this page, subscribe to its [feed](/updates.atom), or watch the repo's
[Announcements](https://github.com/goodgorithm/goodgorithm/discussions/categories/announcements)
on GitHub.

Goodgorithm is in early development, so expect this list to be sparse for now and the app
itself to be rough around the edges.

## 2026-09-08 — The logo learned to wink

The lowercase-`g` mark got a small rework: shift it over, add a left eye, and the
bowl and tail already there become the right eye and a smile — so it reads as a
little winking face as much as a letter. It's in the site header, the browser
tab, and the app's icon now.

## 2026-09-07 — Turning down the promo and bot noise

A run of content-quality reviews turned up a few recurring ways low-value posts
were reaching the top of the feed. Over a few days we shipped fixes for the big
ones:

- "Now playing on `<station>`" radio-bot posts — recognised by their shape and
  pushed down; a repeat offender gets filtered out entirely.
- Bare link-shares, and posts routed through automated RSS-to-social reposters —
  demoted, since there's no personal take in them.
- Prose-y marketing — content-farm "read the full post here", "upvote my product"
  directory posts, affiliate links, asset-store listings — now spotted and demoted.

Each of these lowers a post's rank rather than deleting it, and the whole scoring
adjustment now lives in one auditable place.

## 2026-09-05 — Starting to build our own training data

The models that choose posts — sentiment, topic, category — currently lean on
public datasets that weren't built for a feed like this. We've started keeping a
growing archive of the post text that flows through Goodgorithm (deduplicated,
moderation-passed, with no authors, scores, or engagement attached) so that down
the line we can train text models tuned to what the feed actually sees.

## 2026-09-01 — Roughly 4× more Bluesky posts

The processing pipeline got a profiling-and-tuning pass. Most of its time was
going to database chatter rather than real work; batching that up cut CPU use by
about 6×. With the headroom, we widened how much of Bluesky's firehose we sample
by roughly 4×, so a lot more of what people post now gets considered for the feed.

## 2026-08-28 — Groundwork for native apps

Work started on Capacitor-wrapped iOS and Android builds of the same feed — one codebase,
no separate native app to maintain. They're not in the app stores yet; for now the
"Add to Home Screen" web app is the way to use Goodgorithm on a phone.

## 2026-08-27 — The feed loads faster

The page now paints a skeleton feed almost immediately instead of waiting for the
JavaScript bundle to download first, so there's something on screen sooner on a slow
connection.
