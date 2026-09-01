# Moderation runbook

Operational how-to for the hand-curated moderation tables. **What** each mechanism does and
**why** it's shaped the way it is lives in [`CLAUDE.md`'s Content moderation section](../CLAUDE.md#content-moderation)
and the wiki's [Content Policy](https://github.com/goodgorithm/goodgorithm/wiki/Content-Policy)
page — this file is just the procedure.

There is no admin UI. Edits are made by hand in the Supabase SQL editor, against **both**
the production project **and** its `staging` branch. `processing/` reloads all four lists
within `MODERATION_LISTS_REFRESH_SECONDS` (default 60s) — no deploy or restart needed.

## The tables

| Table | Keyed on | Effect | Catches |
|---|---|---|---|
| `blocked_authors` | `(source, author_id)` | hard exclude | a specific account |
| `suppressed_terms` | `term` (lowercase) | hard exclude | posts whose body hashtags / Mastodon `spoiler_text` contain an unambiguous adult-content self-tag |
| `suppressed_domains` | `domain` (lowercase) | hard exclude | posts linking to the domain (`has_excluded_domain`) **and** Mastodon posts whose account is hosted on it (`has_excluded_home_instance`) |
| `aggregator_instances` | `domain` (lowercase) | **demote only** (`base_score` × `AGGREGATOR_DEMOTE_MULTIPLIER`) | Mastodon posts whose account's home instance is a content aggregator that syndicates headline/link reposts (Flipboard etc.) |

The three hard-exclude tables are **precision over recall, hand-curated**. Add a term/domain
only if it is *definitionally* off-mission — an unambiguous adult self-tag, an instance
dedicated to adult / harassment content, a marketing/affiliate domain. Do **not** add
identity or topic terms that merely correlate ("young", "cub", a political-viewpoint
instance) — those are left to the scoring pipeline.

`aggregator_instances` is a separate, lower-stakes call: a listed instance's posts stay in
the feed, just ranked well down. Add an instance once a measurement pass (see the recurring
query below) shows it contributing a large share of ranked Mastodon volume as automated
syndication with no original commentary — not for being merely prolific or tech-leaning.

## Adding an entry

Run in the SQL editor for the production project, then repeat for the `staging` branch:

```sql
-- blocked_authors
INSERT INTO blocked_authors (source, author_id, reason) VALUES
  ('bluesky', 'did:plc:...', 'Manual moderation: <reason>, <YYYY-MM-DD>')
ON CONFLICT (source, author_id) DO NOTHING;

-- suppressed_terms  (term MUST be lowercase — there's a CHECK constraint)
INSERT INTO suppressed_terms (term, reason) VALUES
  ('somehashtag', '<reason>, <YYYY-MM-DD>')
ON CONFLICT (term) DO NOTHING;

-- suppressed_domains
INSERT INTO suppressed_domains (domain, reason) VALUES
  ('example.com', '<reason>, <YYYY-MM-DD>')
ON CONFLICT (domain) DO NOTHING;

-- aggregator_instances  (demote, not exclude)
INSERT INTO aggregator_instances (domain, reason) VALUES
  ('example.com', 'automated syndication, <share>% of ranked Mastodon volume -- <YYYY-MM-DD>')
ON CONFLICT (domain) DO NOTHING;
```

Always `ON CONFLICT DO NOTHING` and always put a dated `reason` — the table is the audit log.

### `blocked_authors`: block every polled-instance variant of a Mastodon account

`blocked_authors` matches `raw_posts.author_id` **exactly**, and a Mastodon `author_id` is
`{polled_instance}/{acct}` — the same federated account surfaces under a different
`author_id` for each of the 8 polled instances it's visible on. Block all of them:

```sql
INSERT INTO blocked_authors (source, author_id, reason)
SELECT 'mastodon', inst || '/user@home.instance', 'Manual moderation: <reason>, <YYYY-MM-DD>'
FROM unnest(ARRAY[
  'fosstodon.org','hachyderm.io','sciences.social','journa.host',
  'universeodon.com','mstdn.social','mas.to','mastodon.world'
]) AS inst
ON CONFLICT (source, author_id) DO NOTHING;
```

Bluesky `author_id` is a bare DID — one row is enough.

## Purging content already in the DB

Adding an entry only stops **future** posts (and, for `blocked_authors`, triggers a
retroactive sweep). The other two tables have no retroactive sweep — you must delete
existing rows by hand.

- **`blocked_authors`** — `pipeline.purge_blocked_authors()` deletes matching `raw_posts`
  within one processing cycle automatically. Nothing to do; verify it cleared after ~10 min.
- **`suppressed_terms` / `suppressed_domains`** — delete manually. **Preview with `SELECT`
  first**, then `DELETE`. `processed_posts` cascades.
- **`aggregator_instances`** — nothing to purge (it never deleted anything), and nothing to
  do. `aggregator_penalty` is written once when a post is scored, like `link_share_penalty`;
  a new entry applies only to posts scored after the cache refreshes (≤60s), and
  already-scored posts keep their old value until they age out of the 24h retention window.
  Full effect within a day, no manual step.

```sql
-- preview, then swap SELECT ... for DELETE FROM raw_posts r  (keep the WHERE)
SELECT r.id, left(r.text,160) AS text
FROM raw_posts r
WHERE r.raw_json->'account'->>'acct' ~* '@(baddomain\.net)$'          -- home instance
   OR r.text ~* '(baddomain\.net)'                                     -- link in body
   OR r.raw_json->'card'->>'url' ~* '(baddomain\.net)'                 -- Mastodon card
   OR r.raw_json->'record'->'embed'->'external'->>'uri' ~* '(baddomain\.net)'  -- Bluesky embed
   OR r.raw_json->'embed'->'external'->>'uri' ~* '(baddomain\.net)';
```

Match the post's **own** link, not `raw_json::text` — the latter also hits accounts that
merely mention the domain in a profile bio.

## Recurring: new Mastodon instances contributing feed content (#139)

A systematic instance blocklist isn't worth building (see #139 — the off-mission rate in the
tail is ~1 in several hundred). Instead, run this ~monthly and eyeball the delta on two
fronts:

- **Dedicated-adult / harassment-oriented** → `suppressed_domains` (hard exclude).
  Cross-reference only the two small, high-consensus prior-art lists — **Oliphant Tier 0**
  and **Seirdy's FediNuke** — not the broader tiers or aggregate lists (too contested for
  that table's standard).
- **A single instance contributing a large share of `ranked` volume as automated
  headline/link syndication** (high `ranked`, aggregator-shaped content) → `aggregator_instances`
  (demote). `flipboard.com` was ~34% of ranked Mastodon content when this was added (#141).

```sql
WITH masto AS (
  SELECT r.id,
    lower(COALESCE(NULLIF(split_part(r.raw_json->'account'->>'acct','@',2),''),
                   split_part(r.author_id,'/',1))) AS home,
    p.rank_score
  FROM raw_posts r
  LEFT JOIN processed_posts p ON p.raw_post_id = r.id
  WHERE r.source = 'mastodon'
    AND r.ingested_at > '<last review date>'   -- omit for a full snapshot
)
SELECT home,
  count(*) AS raw,
  count(*) FILTER (WHERE rank_score IS NOT NULL) AS ranked,
  round(max(rank_score)::numeric, 2) AS max_rank
FROM masto
GROUP BY home
HAVING count(*) FILTER (WHERE rank_score IS NOT NULL) > 0
ORDER BY ranked DESC;
```

Retention is 24h, so a full snapshot only ever covers the last day; run it often enough that
the windows overlap. Log each pass in the review log below; write up what you found in the
linked issue.

## Recurring: outbound link domains in ranked Mastodon posts

The instance query above is keyed on a post's **home instance**, so it's blind to an account
on a large, legitimate general instance (`mastodon.social`, …) whose *posts* link out to a
dedicated adult / spam / marketing domain. A content farm reachable only by its link
domain — no self-tagged hashtag in `suppressed_terms`, `sensitive` set but the post carries
a link rather than media, home instance a general one — clears every check
`is_content_excluded` runs. Run this alongside the instance query; a link host climbing the
`ranked` column that isn't a normal news/blog/video source is a `suppressed_domains`
candidate (`has_excluded_domain` matches exact-or-subdomain, so list the registrable domain,
not the specific subdomain).

```sql
WITH masto_links AS (
  SELECT r.id,
    lower(regexp_replace(
      substring(COALESCE(NULLIF(r.raw_json->'card'->>'url',''), r.text) FROM 'https?://([^/?#\s]+)'),
      '^www\.', '')) AS link_host,
    p.rank_score
  FROM raw_posts r
  LEFT JOIN processed_posts p ON p.raw_post_id = r.id
  WHERE r.source = 'mastodon'
    AND r.ingested_at > '<last review date>'   -- omit for a full snapshot
)
SELECT link_host,
  count(*) AS raw,
  count(*) FILTER (WHERE rank_score IS NOT NULL) AS ranked,
  round(max(rank_score)::numeric, 2) AS max_rank
FROM masto_links
WHERE link_host IS NOT NULL
GROUP BY link_host
HAVING count(*) FILTER (WHERE rank_score IS NOT NULL) > 0
ORDER BY ranked DESC;
```

Most of the top of that list is legitimate (news sites, `youtube.com`, `github.com`); scan
for the ones that aren't. When one turns up, add it to `suppressed_domains` and purge with
the preview/DELETE query above.

## Recurring: rotating adult / funnel hashtags on Bluesky (#156)

A cross-account OnlyFans/"funnel" pattern on Bluesky — image + short coy caption + a large
bag of hashtags, an "…in my bio" / "one tap away" call to action — rotates its individual
tags faster than any single `suppressed_terms` entry stays current, and its per-post shape
(hashtag count, caption length) is indistinguishable from a legitimate art / photography
tag-dump, so it can't be caught by scoring. `suppressed_terms` is the tool; it needs
periodic topping-up. Run this ~monthly: it lists hashtags co-occurring on Bluesky posts
that already carry a known adult self-tag or a funnel caption, minus the ones already
listed.

```sql
WITH bsky AS (
  SELECT r.id, r.text
  FROM raw_posts r
  WHERE r.source = 'bluesky'
    AND r.ingested_at > '<last review date>'   -- omit for a full snapshot (last 24h)
),
post_tags AS (
  SELECT b.id, lower((regexp_matches(b.text, '#([[:alnum:]_]+)', 'g'))[1]) AS tag
  FROM bsky b
),
funnel_posts AS (
  SELECT DISTINCT pt.id FROM post_tags pt JOIN suppressed_terms s ON s.term = pt.tag
  UNION
  SELECT b.id FROM bsky b WHERE lower(b.text) ~ '(in my bio|one tap away|link in bio)'
)
SELECT pt.tag, count(DISTINCT pt.id) AS posts
FROM post_tags pt
JOIN funnel_posts fp ON fp.id = pt.id
LEFT JOIN suppressed_terms s ON s.term = pt.tag
WHERE s.term IS NULL
GROUP BY pt.tag
HAVING count(DISTINCT pt.id) >= 5
ORDER BY posts DESC;
```

The same precision bar as the table itself: **add only the unambiguous adult / funnel
self-tags** (`egirl`, `curvymodel`, `inkedbabe`, `temptress`, …). The list also surfaces
generic subculture vocabulary the network borrows — `goth`, `gothgirl`, `cosplay`,
`cosplaygirl`, `tattoo`, `tattoolover`, `bikini`, `gym`, `curvy`, `petite`, `altstyle` —
which legitimate goth / cosplay / tattoo / fitness / body-positive accounts also use.
**Do not add those.** When in doubt, check the tag in isolation: pull recent posts
carrying it whose other tags and caption *don't* match the funnel shape; if any are
ordinary content, leave the tag out.

`suppressed_terms` has no retroactive sweep — after adding, purge the network's
already-scored posts with the preview/DELETE query in "Purging content already in the DB".

## Recurring: Bluesky funnel-network cluster review (#162)

`processing/` hard-excludes a Bluesky funnel post per-post (a funnel call-to-action
phrase — "…in my bio", "one tap away" — plus a bag of adult/funnel hashtags), and
`network_detector` separately writes the **DIDs** of accounts posting that shape into
`flagged_author_clusters` so the whole accounts can be blocked wholesale — taking out
their non-funnel posts too and pre-empting the next caption/tag rotation. It **never
auto-blocks**. Check whenever the processing log shows a `bluesky funnel cluster: N DID(s)`
line, or on the same ~monthly cadence as the review above.

The cluster is stored as one row keyed `home_domain = 'bluesky:funnel-network'` (Bluesky
has no home instance; there is one known network — a second would get a second synthetic
key):

```sql
SELECT author_ids, account_count, post_count,
       earliest_account_created_at, latest_account_created_at, updated_at, dismissed_at
FROM flagged_author_clusters
WHERE home_domain = 'bluesky:funnel-network';
```

For this row only, `author_ids` is a list of bare **DIDs**, and
`earliest_/latest_account_created_at` hold the matched posts' `created_at` range (Bluesky
has no account-creation timestamp, and those columns are `NOT NULL`). Spot-check before
blocking:

```sql
SELECT author_id, created_at, left(text, 200) AS text
FROM raw_posts
WHERE source = 'bluesky' AND author_id = ANY (
  SELECT unnest(author_ids) FROM flagged_author_clusters
  WHERE home_domain = 'bluesky:funnel-network')
ORDER BY author_id, created_at DESC;
```

Confirm the coordination — shared verbatim captions across distinct DIDs ("not posting it
twice, check my bio instead 🤫"), near-identical adult tag bags, a bio call-to-action. If
it checks out, bulk-block — one `blocked_authors` row per DID (a Bluesky `author_id` is a
bare DID; no 8-instance `unnest` like Mastodon):

```sql
INSERT INTO blocked_authors (source, author_id, reason)
SELECT 'bluesky', s.did,
       'Manual moderation: coordinated funnel network (funnel CTA + adult tag bag), <YYYY-MM-DD>'
FROM (
  SELECT unnest(author_ids) AS did FROM flagged_author_clusters
  WHERE home_domain = 'bluesky:funnel-network'
) s
ON CONFLICT (source, author_id) DO NOTHING;
```

`purge_blocked_authors()` clears the blocked DIDs' already-ingested posts within one cycle
— nothing to do manually. On the next detection pass the cluster falls below its DID floor
and the row stops refreshing (it keeps its last non-empty counts, same as the Mastodon
path). Once the block has landed, set `dismissed_at = NOW()` on the row to clear it from
your review view.

**Caveat:** there is one `bluesky:funnel-network` row for the whole signal, so
`dismissed_at` on it silences **all** Bluesky funnel detection until cleared back to
`NULL` — only set it after blocking, or if the detector itself is misfiring. To ignore an
individual false-positive DID, just don't block that DID.

### Review log

One row per review pass or moderation action. The **why** — what was sampled, what was
added or rejected and on what evidence — goes in the linked issue or a comment on it, never
in this table.

| Date | Change | Detail |
|---|---|---|
| 2026-08-30 | `yiff.life` → `suppressed_domains` | #139 |
| 2026-08-31 | `channels.im` → `aggregator_instances` | #141 |
| 2026-08-31 | `myxlogs.com` → `suppressed_domains`; `myxlogs@mastodon.social` → `blocked_authors` (all 8 polled instances); outbound-link-domain query added above | [#144 (comment)](https://github.com/goodgorithm/goodgorithm/issues/144#issuecomment-5474399794) |
| 2026-09-01 | 19 adult/funnel hashtags → `suppressed_terms`; Bluesky funnel-hashtag review query added above | #156 |
| 2026-09-01 | Bluesky funnel-network detector + per-post funnel-shape hard-exclude; cluster review section added above | #162 |
