import { test } from "node:test";

import type { FeedRow } from "../src/db";
import { rowToFeedPost } from "../src/feed-post";
import { encodeCursor } from "../src/pagination";
import { FEED_CONTRACT } from "./contracts/android-feed-contract";
import { assertConformsToContract } from "./contracts/assert-contract";

// Guards the /v1/feed response shape the SHIPPED Android app (git tag
// android-v0.1.0) depends on. client.ts does no runtime validation, so a
// dropped or type-changed field breaks every tester with no hotfix. This
// fails if a future change to the row -> FeedPost mapping (or api/src/types.ts)
// stops satisfying FEED_CONTRACT. On an INTENTIONAL contract change the fix
// is a new store build + re-freeze, not editing the assertion away -- see
// web/android/RELEASE.md.

const DID = "did:plc:ibf6ehn7ba3va4jyqhzx6vv3";

function makeRow(overrides: Partial<FeedRow>): FeedRow {
  return {
    id: "row-1",
    source: "bluesky",
    source_id: `${DID}/3msljo7hyxc2o`,
    author_id: DID,
    text: "a genuinely lovely post about a sunrise",
    created_at: new Date("2026-08-28T09:30:00.000Z"),
    entities: null,
    sentiment_score: 0.82,
    topicality_score: 4.1,
    base_score: 3.36,
    rank_score: 3.36,
    pipeline_version: "v5",
    mastodon_permalink: null,
    mastodon_display_name: null,
    mastodon_avatar_url: null,
    bluesky_author_display_name: null,
    bluesky_author_avatar_url: null,
    mastodon_account_emojis: null,
    mastodon_status_emojis: null,
    bluesky_embed: null,
    mastodon_media: null,
    mastodon_card: null,
    mastodon_sensitive: null,
    bluesky_labels: null,
    quote_content: null,
    category: null,
    generated_thumbnail_url: null,
    ...overrides,
  };
}

const FIXTURES: Record<string, FeedRow> = {
  "bluesky minimal (null author, no attachments, null entities)": makeRow({}),

  "bluesky with an image embed": makeRow({
    bluesky_embed: {
      $type: "app.bsky.embed.images",
      images: [{ alt: "a fig basket", image: { ref: { $link: "bafkreihkdhzelfqeomrdx2we476eacogh2uvlddgcnrbu4mkwhnms52osa" } } }],
    },
  }),

  "bluesky with a video embed": makeRow({
    bluesky_embed: {
      $type: "app.bsky.embed.video",
      video: { ref: { $link: "bafkreihcvn3lq7joeciv55ed3qzvich244z62kwzdtyhj2vbcyxsezbdge" }, $type: "blob", mimeType: "video/mp4" },
      aspectRatio: { width: 1080, height: 1920 },
    },
  }),

  "bluesky quote — resolved content available": makeRow({
    bluesky_embed: {
      $type: "app.bsky.embed.record",
      record: { cid: "bafyreie25lnxb35zt4ppydwcgrlw4vgkirbhe5hvtt5kbadrxnhxtmlgwe", uri: "at://did:plc:7gtqafwrxxrqfjeq5vgjauir/app.bsky.feed.post/3msljo7hyxc2o" },
    },
    quote_content: {
      status: "available",
      author: { displayName: "Someone Nice", handle: "someone.bsky.social", avatarUrl: "https://example.com/a.jpg" },
      text: "a genuinely lovely post",
      createdAt: "2026-08-10T12:00:00Z",
    },
  }),

  "bluesky quote — unavailable (not_found)": makeRow({
    bluesky_embed: {
      $type: "app.bsky.embed.record",
      record: { cid: "x", uri: "at://did:plc:abc/app.bsky.feed.post/xyz" },
    },
    quote_content: { status: "unavailable", reason: "not_found" },
  }),

  "mastodon — card + image media + account/status emojis + sensitive + category set": makeRow({
    id: "row-m1",
    source: "mastodon",
    source_id: "fosstodon.org/117071434916343238",
    author_id: "fosstodon.org/someone",
    entities: ["ceasefire", "united nations"],
    mastodon_permalink: "https://fosstodon.org/@someone/117071434916343238",
    mastodon_display_name: "Someone :blobcat:",
    mastodon_avatar_url: "https://cdn.fosstodon.org/avatar.png",
    mastodon_sensitive: true,
    mastodon_account_emojis: [{ shortcode: "blobcat", url: "https://cdn.fosstodon.org/emoji/blobcat.png" }],
    mastodon_status_emojis: [{ shortcode: "sparkle", url: "https://cdn.fosstodon.org/emoji/sparkle.png" }],
    mastodon_media: [
      {
        type: "image",
        url: "https://cdn.fosstodon.org/media/original/e372bdcbd962f24c.jpg",
        preview_url: "https://cdn.fosstodon.org/media/small/e372bdcbd962f24c.jpg",
        description: "Looking down from a 29th floor balcony",
      },
    ],
    mastodon_card: {
      url: "https://jmduke.com/posts/secondhand-time.html",
      title: "Secondhand Time",
      description: "It is rare that I review a book before I finish it.",
      image: "https://media.hachyderm.io/cache/preview_cards/images/052/c48f581a405f9c82.jpg",
      provider_name: "Applied Cartography",
    },
    category: "arts_culture",
  }),
};

for (const [name, row] of Object.entries(FIXTURES)) {
  test(`android-v0.1.0 /v1/feed contract: FeedPost conforms — ${name}`, () => {
    // JSON round-trip = the exact shape a client's response.json() yields.
    const post = JSON.parse(JSON.stringify(rowToFeedPost(row)));
    assertConformsToContract(post, "FeedPost", FEED_CONTRACT);
  });
}

test("android-v0.1.0 /v1/feed contract: FeedResponse envelope (next_cursor null and string)", () => {
  const post = JSON.parse(JSON.stringify(rowToFeedPost(makeRow({}))));

  assertConformsToContract({ posts: [post], next_cursor: null }, "FeedResponse", FEED_CONTRACT);
  assertConformsToContract(
    { posts: [post], next_cursor: encodeCursor({ rank_score: 3.36, id: "row-1" }) },
    "FeedResponse",
    FEED_CONTRACT,
  );
});

test("android-v0.1.0 /v1/feed contract: the asserter itself rejects a missing required field", () => {
  const post = JSON.parse(JSON.stringify(rowToFeedPost(makeRow({}))));
  delete post.permalink;
  try {
    assertConformsToContract(post, "FeedPost", FEED_CONTRACT);
    throw new Error("expected a contract violation for the deleted `permalink`");
  } catch (err) {
    if (!(err instanceof Error) || !err.message.includes("permalink")) throw err;
  }
});
