-- Seed the local dev DB with fake ranked posts so `web/`'s feed renders
-- something without a full ingestion+processing run. Idempotent: re-running
-- replaces its own rows (matched by pipeline_version = 'seed-v1').
--
--   docker exec -i supabase_db_goodgorithm psql -U postgres -d postgres < scripts/seed-local-feed.sql
--
-- Then run `api/` (npm run dev) and `web/` (npm run dev). Remove with:
--   DELETE FROM raw_posts r USING processed_posts p
--   WHERE p.raw_post_id = r.id AND p.pipeline_version = 'seed-v1';

BEGIN;

DELETE FROM raw_posts r
USING processed_posts p
WHERE p.raw_post_id = r.id
  AND p.pipeline_version = 'seed-v1';

WITH params AS (
  SELECT
    i,
    (i % 3 = 0)                                                          AS is_mastodon,
    (ARRAY['arts_culture','science_technology','food_dining','diaries_daily_life',
           'arts_culture','science_technology','food_dining','diaries_daily_life',
           'arts_culture','science_technology','food_dining', NULL])[1 + (i % 12)] AS category,
    now() - (i * interval '17 minutes')                                  AS created_at,
    round((0.95 - i * 0.014)::numeric, 4)::real                          AS rank_score,
    (ARRAY[
      'A stranger paid for my coffee this morning and told me to pass it on. Spent the rest of the day looking for the chance.',
      'The community garden hit its 500th volunteer-hour this weekend. Tomatoes for the whole block.',
      'Researchers just published an open dataset that took a decade to collect. Free for anyone to build on.',
      'My kid taught themselves to solder and fixed the toaster. I have questions but mostly I''m proud.',
      'Local library extended its hours after a fundraiser blew past its goal in two days. People really do love that place.',
      'Watched two rival food trucks lend each other propane during the rush. Small thing, made my week.',
      'The trail crew finished the accessible boardwalk section today. First wheelchair users rolled through at sunset and it was something.',
      'Someone returned my lost wallet with a note: "no need to thank me, just be the person who does this next time." Everything was still in it.',
      'After eighteen months the neighborhood repair cafe has kept an estimated 1.2 tonnes of stuff out of landfill. Mostly kettles and lamps, honestly.',
      'A retired teacher started free evening math tutoring at the rec center. Word spread and now there''s a waitlist and three more volunteers.'
    ])[1 + (i % 10)]                                                     AS body,
    'seed' || lpad(i::text, 2, '0')                                      AS slug
  FROM generate_series(1, 48) AS i
),
raw_ins AS (
  INSERT INTO raw_posts (source, source_id, author_id, text, lang, created_at, raw_json, mastodon_account_created_at)
  SELECT
    CASE WHEN is_mastodon THEN 'mastodon' ELSE 'bluesky' END,
    CASE WHEN is_mastodon
         THEN format('https://mastodon.example/@%s/%s', slug, i)
         ELSE format('did:plc:%s/3%srkey', slug, slug) END,
    CASE WHEN is_mastodon
         THEN format('mastodon.example/%s', slug)
         ELSE format('did:plc:%s', slug) END,
    body,
    'en',
    created_at,
    CASE
      WHEN is_mastodon AND i % 6 = 0 THEN jsonb_build_object(
        'url', format('https://mastodon.example/@%s/%s', slug, i),
        'account', jsonb_build_object('display_name', format('Seed User %s', i), 'avatar', null),
        'media_attachments', jsonb_build_array(jsonb_build_object(
          'type', 'image',
          'url', format('https://picsum.photos/seed/%s/900/560', slug),
          'preview_url', format('https://picsum.photos/seed/%s/450/280', slug),
          'description', 'Placeholder image'
        ))
      )
      WHEN is_mastodon THEN jsonb_build_object(
        'url', format('https://mastodon.example/@%s/%s', slug, i),
        'account', jsonb_build_object('display_name', format('Seed User %s', i), 'avatar', null)
      )
      WHEN i % 6 = 3 THEN jsonb_build_object('commit', jsonb_build_object('record', jsonb_build_object(
        'embed', jsonb_build_object(
          '$type', 'app.bsky.embed.external',
          'external', jsonb_build_object(
            'uri', 'https://example.com/good-news',
            'title', format('Seed link card %s', i),
            'description', 'A short standing-in description for the linked article.'
          )
        )
      )))
      ELSE jsonb_build_object('commit', jsonb_build_object('record', jsonb_build_object()))
    END,
    NULL
  FROM params
  RETURNING id, source, source_id, (regexp_match(source_id, 'seed[0-9]+'))[1] AS slug
)
INSERT INTO processed_posts (
  raw_post_id, dedup_cluster_id, is_dedup_canonical, is_bot,
  sentiment_score, sentiment_method, topicality_score, entities,
  base_score, rank_score, pipeline_version, category, category_method,
  bluesky_author, generated_thumbnail_url
)
SELECT
  r.id,
  gen_random_uuid(),
  true,
  false,
  round((0.55 + 0.4 * (p.i % 5) / 4.0)::numeric, 4)::real,
  'seed',
  round((0.15 + 0.75 * (p.i % 7) / 6.0)::numeric, 4)::real,
  to_jsonb((ARRAY['Community','Science','Neighbours','Volunteers','Libraries','Repair'])[1 + (p.i % 6):2 + (p.i % 6)]),
  p.rank_score + 0.02,
  p.rank_score,
  'seed-v1',
  p.category,
  CASE WHEN p.category IS NULL THEN NULL ELSE 'seed' END,
  CASE WHEN r.source = 'bluesky'
       THEN jsonb_build_object('displayName', format('Seed User %s', p.i), 'avatarUrl', null)
       ELSE NULL END,
  CASE WHEN r.source = 'bluesky' AND p.i % 6 = 3
       THEN format('https://picsum.photos/seed/%s/600/315', p.slug)
       ELSE NULL END
FROM raw_ins r
JOIN params p ON p.slug = r.slug;

COMMIT;

SELECT category, count(*), round(min(rank_score)::numeric, 3) AS min_rank, round(max(rank_score)::numeric, 3) AS max_rank
FROM processed_posts WHERE pipeline_version = 'seed-v1'
GROUP BY category ORDER BY category NULLS LAST;
