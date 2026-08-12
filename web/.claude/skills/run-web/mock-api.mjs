// Minimal stand-in for api/'s /health and /feed, for driving web/ without a
// real Postgres-backed api/ instance. Shapes match web/src/api/types.ts's
// FeedResponse/FeedPost - keep in sync if that type changes. Not part of the
// app - agent tooling only. See SKILL.md.
//
// Usage: node mock-api.mjs [port]  (default 4100)

import http from "node:http";

const PORT = Number(process.argv[2]) || 4100;
const PAGE_SIZE = 20;

// Mirrors web/src/api/types.ts's CATEGORIES - keep in sync if that changes.
const CATEGORIES = [
  "technology",
  "arts_culture",
  "animals",
  "science_discovery",
  "kindness_community",
  "environment_nature",
  "health_recovery",
  "sports_achievement",
];

const LONG_TEXT =
  "Neighbors on Elm Street spent the whole weekend rebuilding the community garden after the storm knocked over half the raised beds. " +
  "Someone brought a truckload of compost, someone else donated seedlings, and by Sunday evening there were fresh rows of tomatoes, peppers, and squash going in the ground. " +
  "A few kids from the block painted a new sign for the entrance gate, and one of the older residents who used to run a nursery spent hours teaching everyone how to properly stake the young plants. " +
  "By the time the sun went down, thirty-some people who barely knew each other a month ago were sitting together sharing lemonade and planning the next work day. " +
  "It's a small thing in the scheme of the world, but it's the kind of small thing that adds up.";

function makePosts(count) {
  const posts = [];
  for (let i = 0; i < count; i++) {
    const isLong = i === 3; // one long post, to exercise auto-collapse
    const hasVideo = i === 5; // one video post, to exercise the lazy-loaded VideoPlayer/hls.js chunk
    // every 5th post uncategorized (category: null), matching real data
    // where a lot of content doesn't match any taxonomy term.
    const category = i % 5 === 0 ? null : CATEGORIES[i % CATEGORIES.length];
    posts.push({
      id: String(i),
      source: i % 2 === 0 ? "bluesky" : "mastodon",
      author_id: `user-${i}`,
      text: isLong ? LONG_TEXT : `Short uplifting post number ${i} (${category ?? "uncategorized"}).`,
      created_at: new Date(Date.now() - i * 60_000).toISOString(),
      entities: [],
      permalink: `https://example.com/post/${i}`,
      author: { display_name: `Person ${i}`, avatar_url: null },
      // Varies across posts so the score bars' fill levels actually differ
      // instead of every card looking identical. Sentiment stays within the
      // realistic post-eligibility range (0.3-1.0, see ranking.py's
      // POSITIVITY_THRESHOLD); topicality/base/rank are unbounded in the
      // real pipeline, so these are just varied enough to exercise the
      // per-batch percentile bars (web/src/lib/scoreScale.ts) with real
      // spread within each 20-post page.
      scores: {
        sentiment: 0.3 + ((i * 0.13) % 0.7),
        topicality: 0.4 + ((i * 0.37) % 1.6),
        base: 0.2 + ((i * 0.29) % 1.1),
        rank: 1 - ((i * 0.17) % 1),
      },
      pipeline_version: "v1",
      attachments: hasVideo
        ? [
            {
              kind: "video",
              // A plain MP4 (Mastodon-shaped) so this exercises VideoPlayer's
              // native <video src> path without needing a real HLS manifest.
              playlistUrl: "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
              thumbnailUrl: null,
              isGif: false,
              width: 1280,
              height: 720,
            },
          ]
        : [],
      sensitive: false,
      category,
    });
  }
  return posts;
}

const ALL_POSTS = makePosts(60);

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  res.setHeader("Access-Control-Allow-Origin", "*");

  if (url.pathname === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok" }));
    return;
  }

  if (url.pathname === "/feed") {
    const category = url.searchParams.get("category");
    const filtered = category ? ALL_POSTS.filter((p) => p.category === category) : ALL_POSTS;
    const cursor = url.searchParams.get("cursor");
    const start = cursor ? Number(cursor) : 0;
    const page = filtered.slice(start, start + PAGE_SIZE);
    const nextIndex = start + PAGE_SIZE;
    const next_cursor = nextIndex < filtered.length ? String(nextIndex) : null;
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ posts: page, next_cursor }));
    return;
  }

  res.writeHead(404);
  res.end();
});

server.listen(PORT, () => console.log(`mock api listening on ${PORT}`));
