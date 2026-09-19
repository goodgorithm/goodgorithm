# Political / civic tone — labeling guide

Companion to `political_tone_eval.jsonl` (1181 posts, maintainer-confirmed), the hand-labeled
evaluation set for political/civic content used by the
[#228](https://github.com/goodgorithm/goodgorithm/issues/228) research epic. Reusable for any
future labeling pass on this taxonomy.

## Categories

- **`non-political`** — no political/civic content, including a post with an incidental political
  word or hashtag that isn't actually about anything political (a coincidental hashtag on an
  unrelated greeting, a nostalgia post that happens to mention "politicians" in passing).
- **`civic-neutral`** — political-topic but flat/informational: straight news coverage, election
  logistics, get-out-the-vote PSAs and registration-drive announcements with no candidate or
  partisan framing attached.
- **`civic-warm`** — genuine positivity *about* civic life, not political cheerleading: a
  naturalization-ceremony photo, a first-time voter's excitement, a local organizer winning a
  race, a volunteer poll-worker thank-you, a cultural/civic holiday celebration.
- **`civic-negative`** — everything else politically charged: advocacy/mobilizing content tied to
  a specific candidate or partisan framing, outrage, mockery, partisan cheerleading (including
  "thank you [politician]" posts whose entire content is political gratitude), and
  partisan-identity merchandise/promotion.

## Worked examples

**`non-political`**
- "Good morning peeps💙 #Midterms" — the hashtag is coincidental, not about anything political.
- A Jets/Giants nostalgia post mentioning "competent politicians" in passing — the political
  phrase is incidental to otherwise-unrelated sports content.
- A self-promo video that happens to mention a specific election in passing, where the election
  isn't what the post is about.

**`civic-neutral`**
- A get-out-the-vote / National Voter Registration Day PSA with no candidate or partisan framing
  — read as neutral civic-info content, not advocacy, even though it's technically "mobilizing."
- A post relaying someone else's political statement as reported speech (e.g. quoting a public
  figure) rather than the poster's own advocacy or commentary.
- Straight news-link posts about a political event with no visible editorializing.

**`civic-warm`**
- A naturalization-ceremony photo; "my daughter registered to vote for the first time 🥹."
- A local organizer or first-time candidate winning a small race, framed as community pride.
- A cultural/national holiday celebration (e.g. an Independence Day post) with genuine warmth
  and no partisan angle.

**`civic-negative`**
- Outrage or mockery, even in positive-coded language ("😂😂 MAGA in a nutshell. Hilarious.").
- Advocacy tied to a specific candidate or party ("Call your rep and vote no," campaign
  promotion, partisan-identity merchandise ads).
- Brief "thank you [politician]" posts whose *entire* content is political gratitude — reads as
  partisan cheerleading, not genuine warmth, when there's nothing else attached.
- Posts referencing a public figure's age/health as a pointed jab rather than genuine concern.

## Boundary cases — the ones worth double-checking

- **Civic-warm vs. civic-negative is the hardest real distinction.** A "thank you [politician]"
  post with *nothing else attached* defaults to `civic-negative` (partisan cheerleading), but a
  very short, generic thank-you with no partisan markers can reasonably read as `civic-neutral`
  instead — judge by how contentful and partisan-coded the gratitude actually is, not just its
  polarity.
- **Voter-registration-day PSAs default to `civic-neutral`, not `civic-negative`**, unless tied to
  a specific candidate or explicit partisan framing — get-out-the-vote content is not the same as
  candidate advocacy.
- **Partisan-identity merchandise/promotion is `civic-negative`, not `non-political`** — treat it
  as political content in its own right, not a false positive, even when it's phrased as an ad.
- **Political-club and voter-registration posts can read as `civic-warm` on a closer look** if the
  framing is genuinely about community participation rather than mobilization or partisanship.
- **Don't miss the linked content.** For a bare-link post, the linked article's own title/content
  is part of what determines the label — a link-only post shouldn't be labeled on the surrounding
  text alone if the link itself is clearly political.
- **Generic-word false positives**: "campaign," "party," "state," "bill," "house" all have
  dominant non-political senses (a TTRPG campaign, a birthday party). Read for actual political
  content, not keyword presence.

## Dataset format

`political_tone_eval.jsonl` — one JSON object per line: `text`, `label`, `source`
(`bluesky`/`mastodon`), `created_at` (the post's original creation time, for stratified analysis).
No author identity, no engagement counts — matches the project's general no-engagement-signals
discipline and the [#177](https://github.com/goodgorithm/goodgorithm/issues/177) corpus's own
privacy stance. Every row is a maintainer-confirmed label (AI-drafted suggestions that weren't
subsequently reviewed by a maintainer are not included).
