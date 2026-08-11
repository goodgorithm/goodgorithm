// Minimal stand-in for api/'s /health and /feed, for driving web/ without a
// real Postgres-backed api/ instance. Shapes match web/src/api/types.ts's
// FeedResponse/FeedPost - keep in sync if that type changes. Not part of the
// app - agent tooling only. See SKILL.md.
//
// Usage: node mock-api.mjs [port]  (default 4100)

import http from "node:http";

const PORT = Number(process.argv[2]) || 4100;
const PAGE_SIZE = 20;

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
    posts.push({
      id: String(i),
      source: i % 2 === 0 ? "bluesky" : "mastodon",
      author_id: `user-${i}`,
      text: isLong ? LONG_TEXT : `Short uplifting post number ${i}.`,
      created_at: new Date(Date.now() - i * 60_000).toISOString(),
      entities: [],
      permalink: `https://example.com/post/${i}`,
      author: { display_name: `Person ${i}`, avatar_url: null },
      scores: { sentiment: 0.8, topicality: 1, base: 0.9, rank: 1 - i * 0.001 },
      attachments: [],
      sensitive: false,
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
    const cursor = url.searchParams.get("cursor");
    const start = cursor ? Number(cursor) : 0;
    const page = ALL_POSTS.slice(start, start + PAGE_SIZE);
    const nextIndex = start + PAGE_SIZE;
    const next_cursor = nextIndex < ALL_POSTS.length ? String(nextIndex) : null;
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ posts: page, next_cursor }));
    return;
  }

  res.writeHead(404);
  res.end();
});

server.listen(PORT, () => console.log(`mock api listening on ${PORT}`));
