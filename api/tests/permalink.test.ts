import assert from "node:assert/strict";
import { test } from "node:test";

import { buildPermalink } from "../src/permalink";

test("builds a bsky.app permalink from a Bluesky source_id", () => {
  const permalink = buildPermalink({
    source: "bluesky",
    source_id: "did:plc:5zww7zorx2ajw7hqrhuix3ba/3l6abcdefgh2x",
    mastodon_permalink: null,
  });
  assert.equal(
    permalink,
    "https://bsky.app/profile/did:plc:5zww7zorx2ajw7hqrhuix3ba/post/3l6abcdefgh2x",
  );
});

test("returns the stored permalink for a Mastodon post", () => {
  const permalink = buildPermalink({
    source: "mastodon",
    source_id: "fosstodon.org/12345",
    mastodon_permalink: "https://fosstodon.org/@someone/12345",
  });
  assert.equal(permalink, "https://fosstodon.org/@someone/12345");
});

test("falls back to an empty string when a Mastodon permalink is missing", () => {
  const permalink = buildPermalink({
    source: "mastodon",
    source_id: "fosstodon.org/12345",
    mastodon_permalink: null,
  });
  assert.equal(permalink, "");
});
