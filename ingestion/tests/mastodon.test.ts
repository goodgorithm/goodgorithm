import assert from "node:assert/strict";
import { test } from "node:test";

import { isDiscoverable, stripHtml } from "../src/mastodon";

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

test("stripHtml reconstructs a URL Mastodon splits across invisible/ellipsis spans (issue #22)", () => {
  // Real markup pulled from production raw_posts.raw_json->>'content'.
  const html =
    '<p>Greenland forces Trump-linked US oil firm to delay drilling | Greenland | The Guardian <br>' +
    '<a href="https://www.theguardian.com/world/2026/aug/12/trump-greenland-oil" rel="nofollow noopener" translate="no" target="_blank">' +
    '<span class="invisible">https://www.</span>' +
    '<span class="ellipsis">theguardian.com/world/2026/aug</span>' +
    '<span class="invisible">/12/trump-greenland-oil</span>' +
    "</a></p>";

  assert.equal(
    stripHtml(html),
    "Greenland forces Trump-linked US oil firm to delay drilling | Greenland | The Guardian " +
      "https://www.theguardian.com/world/2026/aug/12/trump-greenland-oil",
  );
});

test("stripHtml reconstructs hashtags Mastodon wraps in a nested span (issue #22)", () => {
  const html =
    '<p><a href="https://masto.ai/tags/Greenland" class="mention hashtag" rel="nofollow noopener" target="_blank">#<span>Greenland</span></a> ' +
    '<a href="https://masto.ai/tags/Trump" class="mention hashtag" rel="nofollow noopener" target="_blank">#<span>Trump</span></a></p>';

  assert.equal(stripHtml(html), "#Greenland #Trump");
});

test("isDiscoverable is true when both fields are opted in (issue #25)", () => {
  assert.equal(isDiscoverable({ discoverable: true, indexable: true }), true);
});

test("isDiscoverable is false when discoverable is explicitly false", () => {
  assert.equal(isDiscoverable({ discoverable: false, indexable: true }), false);
});

test("isDiscoverable is false when indexable is explicitly false, even if discoverable is true", () => {
  // The more common real-world case (see mastodon.ts's comment): opted into
  // the profile directory but explicitly opted out of search-engine/external
  // indexing.
  assert.equal(isDiscoverable({ discoverable: true, indexable: false }), false);
});

test("isDiscoverable is false when both fields are explicitly false", () => {
  assert.equal(isDiscoverable({ discoverable: false, indexable: false }), false);
});

test("isDiscoverable treats null (unset) fields as opted-in by default", () => {
  assert.equal(isDiscoverable({ discoverable: null, indexable: null }), true);
  assert.equal(isDiscoverable({ discoverable: null, indexable: true }), true);
  assert.equal(isDiscoverable({ discoverable: true, indexable: null }), true);
});
