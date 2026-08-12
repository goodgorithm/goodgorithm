import assert from "node:assert/strict";
import { test } from "node:test";

import { stripHtml } from "../src/mastodon";

test("stripHtml strips tags", () => {
  assert.equal(stripHtml("<p>Hello <strong>world</strong></p>"), "Hello world");
});

test("stripHtml decodes named HTML entities", () => {
  assert.equal(stripHtml("<p>Fish &amp; chips</p>"), "Fish & chips");
  assert.equal(stripHtml("<p>&lt;script&gt;</p>"), "<script>");
  assert.equal(stripHtml("<p>&quot;quoted&quot; and it&apos;s fine</p>"), '"quoted" and it\'s fine');
});

test("stripHtml decodes numeric and hex entities", () => {
  assert.equal(stripHtml("<p>caf&#233;</p>"), "café");
  assert.equal(stripHtml("<p>caf&#xe9;</p>"), "café");
});

test("stripHtml collapses &nbsp; into a single space alongside real whitespace", () => {
  assert.equal(stripHtml("<p>a&nbsp;&nbsp;b</p>"), "a b");
});

test("stripHtml leaves an unrecognized entity untouched", () => {
  assert.equal(stripHtml("<p>&notareal;</p>"), "&notareal;");
});

test("stripHtml returns an empty string for tags-only content", () => {
  assert.equal(stripHtml("<p></p>"), "");
});
