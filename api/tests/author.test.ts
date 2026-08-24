import assert from "node:assert/strict";
import { test } from "node:test";

import { buildAuthor } from "../src/author";

test("returns Mastodon's author fields when present", () => {
  const author = buildAuthor({
    mastodon_display_name: "Jane Doe",
    mastodon_avatar_url: "https://fosstodon.org/avatar.jpg",
    bluesky_author_display_name: null,
    bluesky_author_avatar_url: null,
    mastodon_account_emojis: null,
  });
  assert.deepEqual(author, {
    display_name: "Jane Doe",
    avatar_url: "https://fosstodon.org/avatar.jpg",
    emojis: [],
  });
});

test("falls back to a resolved Bluesky author when Mastodon fields are null", () => {
  const author = buildAuthor({
    mastodon_display_name: null,
    mastodon_avatar_url: null,
    bluesky_author_display_name: "Jane Doe",
    bluesky_author_avatar_url: "https://cdn.bsky.app/avatar.jpg",
    mastodon_account_emojis: null,
  });
  assert.deepEqual(author, {
    display_name: "Jane Doe",
    avatar_url: "https://cdn.bsky.app/avatar.jpg",
    emojis: [],
  });
});

test("is all-null for an unresolved or unresolvable Bluesky post", () => {
  const author = buildAuthor({
    mastodon_display_name: null,
    mastodon_avatar_url: null,
    bluesky_author_display_name: null,
    bluesky_author_avatar_url: null,
    mastodon_account_emojis: null,
  });
  assert.deepEqual(author, { display_name: null, avatar_url: null, emojis: [] });
});

test("resolves a Mastodon custom-emoji shortcode used in the display name (issue #77)", () => {
  const author = buildAuthor({
    mastodon_display_name: "Volodymyr Zelenskyy :bot:",
    mastodon_avatar_url: null,
    bluesky_author_display_name: null,
    bluesky_author_avatar_url: null,
    mastodon_account_emojis: [{ shortcode: "bot", url: "https://zpravobot.news/emoji/bot.png" }],
  });
  assert.deepEqual(author, {
    display_name: "Volodymyr Zelenskyy :bot:",
    avatar_url: null,
    emojis: [{ shortcode: "bot", url: "https://zpravobot.news/emoji/bot.png" }],
  });
});
