import assert from "node:assert/strict";
import { test } from "node:test";

import { blockedAuthorsCacheStale, isBlockedAuthor } from "../src/db";

test("isBlockedAuthor matches a Bluesky DID in the set", () => {
  const blocked = new Set(["bluesky\tdid:plc:abc123"]);
  assert.equal(isBlockedAuthor("bluesky", "did:plc:abc123", blocked), true);
});

test("isBlockedAuthor matches a Mastodon {instance}/{acct} author_id", () => {
  const blocked = new Set(["mastodon\tmas.to/spammer@pubeurope.com"]);
  assert.equal(isBlockedAuthor("mastodon", "mas.to/spammer@pubeurope.com", blocked), true);
});

test("isBlockedAuthor is source-scoped -- same author_id string, wrong source", () => {
  const blocked = new Set(["mastodon\tdid:plc:abc123"]);
  assert.equal(isBlockedAuthor("bluesky", "did:plc:abc123", blocked), false);
});

test("isBlockedAuthor is false for an author not in the set, and for an empty set", () => {
  assert.equal(isBlockedAuthor("bluesky", "did:plc:notblocked", new Set(["bluesky\tdid:plc:other"])), false);
  assert.equal(isBlockedAuthor("mastodon", "mas.to/anyone@example.com", new Set()), false);
});

// MODERATION_LISTS_REFRESH_SECONDS default is 60s (60000ms).
test("blockedAuthorsCacheStale is false within the refresh window", () => {
  assert.equal(blockedAuthorsCacheStale(1_000_000, 1_059_999), false);
});

test("blockedAuthorsCacheStale is true at and past the refresh window", () => {
  assert.equal(blockedAuthorsCacheStale(1_000_000, 1_060_000), true);
  assert.equal(blockedAuthorsCacheStale(1_000_000, 5_000_000), true);
});
