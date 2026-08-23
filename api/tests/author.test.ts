import assert from "node:assert/strict";
import { test } from "node:test";

import { buildAuthor } from "../src/author";

test("returns Mastodon's author fields when present", () => {
  const author = buildAuthor({
    mastodon_display_name: "Jane Doe",
    mastodon_avatar_url: "https://fosstodon.org/avatar.jpg",
    bluesky_author_display_name: null,
    bluesky_author_avatar_url: null,
  });
  assert.deepEqual(author, {
    display_name: "Jane Doe",
    avatar_url: "https://fosstodon.org/avatar.jpg",
  });
});

test("falls back to a resolved Bluesky author when Mastodon fields are null", () => {
  const author = buildAuthor({
    mastodon_display_name: null,
    mastodon_avatar_url: null,
    bluesky_author_display_name: "Jane Doe",
    bluesky_author_avatar_url: "https://cdn.bsky.app/avatar.jpg",
  });
  assert.deepEqual(author, {
    display_name: "Jane Doe",
    avatar_url: "https://cdn.bsky.app/avatar.jpg",
  });
});

test("is all-null for an unresolved or unresolvable Bluesky post", () => {
  const author = buildAuthor({
    mastodon_display_name: null,
    mastodon_avatar_url: null,
    bluesky_author_display_name: null,
    bluesky_author_avatar_url: null,
  });
  assert.deepEqual(author, { display_name: null, avatar_url: null });
});
