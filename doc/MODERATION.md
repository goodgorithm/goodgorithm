# Moderation runbook

Operational how-to for the hand-curated moderation tables. **What** each mechanism does and
**why** it's shaped the way it is lives in [`CLAUDE.md`'s Content moderation section](../CLAUDE.md#content-moderation)
and the wiki's [Content Policy](https://github.com/goodgorithm/goodgorithm/wiki/Content-Policy)
page — this file is just the procedure.

There is no admin UI. Edits are made by hand in the Supabase SQL editor, against **both**
the production project **and** its `staging` branch. `processing/` reloads all three lists
within `MODERATION_LISTS_REFRESH_SECONDS` (default 60s) — no deploy or restart needed.

## The three tables

| Table | Keyed on | Catches |
|---|---|---|
| `blocked_authors` | `(source, author_id)` | a specific account |
| `suppressed_terms` | `term` (lowercase) | posts whose body hashtags / Mastodon `spoiler_text` contain an unambiguous adult-content self-tag |
| `suppressed_domains` | `domain` (lowercase) | posts linking to the domain (`has_excluded_domain`) **and** Mastodon posts whose account is hosted on it (`has_excluded_home_instance`) |

All three are **precision over recall, hand-curated**. Add a term/domain only if it is
*definitionally* off-mission — an unambiguous adult self-tag, an instance dedicated to adult
/ harassment content, a marketing/affiliate domain. Do **not** add identity or topic terms
that merely correlate ("young", "cub", a political-viewpoint instance) — those are left to
the scoring pipeline.

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
tail is ~1 in several hundred). Instead, run this ~monthly and eyeball the delta for
anything dedicated-adult / harassment-oriented. Cross-reference only the two small,
high-consensus prior-art lists — **Oliphant Tier 0** and **Seirdy's FediNuke** — not the
broader tiers or aggregate lists (too contested for this table's standard).

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
the windows overlap. Record the date of each review here or in the #139 thread.

### Review log

| Date | Reviewer | Added | Notes |
|---|---|---|---|
| 2026-08-30 | initial (#139) | `yiff.life` (`suppressed_domains`) | Full snapshot of ~1,100 instances / 318 ranked-contributing. Only `yiff.life` (dedicated furry-NSFW, 0 ranked, precautionary). `kinkycats.org` reviewed and **not** added — sex-positive general community, benign content. No hate instances present (already defederated upstream by the 8 polled instances). |
