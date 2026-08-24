// Minimal stand-in for api/'s /health and /feed, for driving web/ without a
// real Postgres-backed api/ instance. Shapes match web/src/api/types.ts's
// FeedResponse/FeedPost - keep in sync if that type changes. Shared between
// the run-web agent skill (../.claude/skills/run-web/SKILL.md) and the
// Playwright E2E suite (playwright.config.ts's webServer) - one canonical
// mock backend, not two copies to keep in sync.
//
// Usage: node mock-api.mjs [port]  (default 4100)

import http from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const PORT = Number(process.argv[2]) || 4100;
const PAGE_SIZE = 20;
const FIXTURES_DIR = fileURLToPath(new URL("./fixtures", import.meta.url));

// Mirrors web/src/api/types.ts's CATEGORIES - keep in sync if that changes.
const CATEGORIES = ["science_technology", "arts_culture", "food_dining", "diaries_daily_life"];

// A minimal 1x1 PNG, used as a stand-in custom-emoji image (issue #77) -
// a data: URI needs no network fetch, keeping the mock fully offline.
const EMOJI_DATA_URI =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

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
    const hasVideo = i === 5 || i === 7; // one video post, to exercise the lazy-loaded VideoPlayer/hls.js chunk
    const hasGifVideo = i === 6; // one gif-style video, to exercise the pause/play toggle
    // A real, locally-served HLS stream (web/e2e/fixtures/hls/) behind a
    // sensitive-reveal toggle -- covers both issue #66 regressions in one
    // post: hls.js actually engaging (not silently falling back to a native
    // <video src> that can't play HLS) and SensitiveMedia's reveal not
    // remounting VideoPlayer (which used to destroy the hls.js attachment).
    const hasRealHlsVideo = i === 12;
    const isSensitive = i === 7 || i === 12; // exercise the reveal/re-hide toggle
    const hasLink = i === 8; // one post with a URL + hashtag, to exercise linkify
    // One Mastodon post with a custom-emoji shortcode in both its display
    // name and its own text (issue #77) - exercises renderEmojiShortcodes
    // in both call sites and its composition with linkify in the post-text
    // case (i === 11 is odd, i.e. "mastodon" per the source calc below -
    // Bluesky has no custom-emoji concept, so this only makes sense there).
    const hasEmoji = i === 11;
    // every 5th post uncategorized (category: null), matching real data
    // where a lot of content doesn't match any taxonomy term.
    const category = i % 5 === 0 ? null : CATEGORIES[i % CATEGORIES.length];
    const source = i % 2 === 0 ? "bluesky" : "mastodon";
    posts.push({
      id: String(i),
      source,
      author_id: `user-${i}`,
      text: isLong
        ? LONG_TEXT
        : hasLink
          ? `Loving this #goodnews today - check it out at https://example.com/story.`
          : hasEmoji
            ? `So happy right now :blobcat: check this out https://example.com/story`
            : `Short uplifting post number ${i} (${category ?? "uncategorized"}).`,
      created_at: new Date(Date.now() - i * 60_000).toISOString(),
      entities: [],
      permalink: source === "mastodon" ? `https://fosstodon.org/@user${i}/${i}` : `https://example.com/post/${i}`,
      author: {
        display_name: hasEmoji ? `Person ${i} :bot:` : `Person ${i}`,
        avatar_url: null,
        // A tiny inline data: URI, not a real Mastodon CDN URL - keeps this
        // mock fully offline (no network dependency for the driver/E2E
        // suite to flake on), unlike every other image field here which
        // points at a real or fixture URL.
        emojis: hasEmoji ? [{ shortcode: "bot", url: EMOJI_DATA_URI }] : [],
      },
      emojis: hasEmoji ? [{ shortcode: "blobcat", url: EMOJI_DATA_URI }] : [],
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
      attachments: hasVideo || hasGifVideo || hasRealHlsVideo
        ? [
            {
              kind: "video",
              playlistUrl: hasRealHlsVideo
                ? `http://localhost:${PORT}/fixtures/hls/playlist.m3u8`
                // A plain MP4 (Mastodon-shaped) so this exercises VideoPlayer's
                // native <video src> path without needing a real HLS manifest.
                : "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
              thumbnailUrl: null,
              isGif: hasGifVideo,
              width: hasRealHlsVideo ? 320 : 1280,
              height: hasRealHlsVideo ? 240 : 720,
            },
          ]
        : [],
      sensitive: isSensitive,
      category,
    });
  }
  return posts;
}

// 105, not 60 -- every real category needs strictly more than PAGE_SIZE
// (20) posts for e2e/feed.spec.ts's infinite-scroll test to have a real
// second page to fetch (each category gets ~21 of every 105, see the i%5
// null-exclusion above).
const ALL_POSTS = makePosts(105);

// Serves web/e2e/fixtures/ verbatim -- currently just the HLS test stream
// (fixtures/hls/playlist.m3u8 + segment*.ts), generated once via ffmpeg, not
// regenerated at request time. No directory traversal beyond fixtures/: the
// path is resolved but not validated against `..` since this only ever
// serves a fixed, repo-controlled set of filenames, never user input.
const FIXTURE_MIME_TYPES = { ".m3u8": "application/vnd.apple.mpegurl", ".ts": "video/mp2t" };

async function serveFixture(pathname, res) {
  const ext = pathname.slice(pathname.lastIndexOf("."));
  const contentType = FIXTURE_MIME_TYPES[ext];
  if (!contentType) {
    res.writeHead(404);
    res.end();
    return;
  }
  try {
    const body = await readFile(`${FIXTURES_DIR}${pathname.replace("/fixtures", "")}`);
    res.writeHead(200, { "Content-Type": contentType });
    res.end(body);
  } catch {
    res.writeHead(404);
    res.end();
  }
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  res.setHeader("Access-Control-Allow-Origin", "*");

  if (url.pathname.startsWith("/fixtures/")) {
    void serveFixture(url.pathname, res);
    return;
  }

  if (url.pathname === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok" }));
    return;
  }

  if (url.pathname === "/v1/feed") {
    // ?fail=1 - agent tooling hook to exercise FeedError's retry button
    // without needing a real backend failure.
    if (url.searchParams.get("fail") === "1") {
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "simulated failure" }));
      return;
    }
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
