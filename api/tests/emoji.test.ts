import assert from "node:assert/strict";
import { test } from "node:test";

import { buildEmojis } from "../src/emoji";

test("returns [] for a non-array (e.g. a Bluesky row, which has no emojis field)", () => {
  assert.deepEqual(buildEmojis(null), []);
  assert.deepEqual(buildEmojis(undefined), []);
  assert.deepEqual(buildEmojis("not an array"), []);
});

test("maps a well-formed emoji entry to {shortcode, url}", () => {
  const raw = [
    { shortcode: "bot", url: "https://example.com/bot.png", static_url: "https://example.com/bot.png", visible_in_picker: true },
  ];
  assert.deepEqual(buildEmojis(raw), [{ shortcode: "bot", url: "https://example.com/bot.png" }]);
});

test("drops an entry with a non-http(s) url", () => {
  const raw = [{ shortcode: "bot", url: "javascript:alert(1)" }];
  assert.deepEqual(buildEmojis(raw), []);
});

test("drops a malformed entry (missing shortcode, non-object item) without throwing", () => {
  const raw = [null, "not an object", { url: "https://example.com/a.png" }, { shortcode: "" }, 42];
  assert.deepEqual(buildEmojis(raw), []);
});

test("preserves order and keeps multiple valid entries", () => {
  const raw = [
    { shortcode: "wave", url: "https://example.com/wave.png" },
    { shortcode: "blobcat", url: "https://example.com/blobcat.png" },
  ];
  assert.deepEqual(buildEmojis(raw), [
    { shortcode: "wave", url: "https://example.com/wave.png" },
    { shortcode: "blobcat", url: "https://example.com/blobcat.png" },
  ]);
});
