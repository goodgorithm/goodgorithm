import assert from "node:assert/strict";
import { test } from "node:test";

import { resolveFacetLinks } from "../src/bluesky";

test("resolveFacetLinks substitutes a facet-marked truncated link with its real URI (issue #42)", () => {
  // Real text + facet pulled from production (the reported post): the
  // poster's own client shortened the visible mention to
  // "openai.com/index/unders...", but the facet carries the real target.
  const text =
    "Meanwhile, OpenAI is running a massive experiment in both AI instruction and AI learning measurement in Estonia. " +
    "So new evidence practices, measurement instruments and experiments in AI evaluation in education are proliferating right now openai.com/index/unders...";
  const facets = [
    {
      index: { byteStart: 238, byteEnd: 264 },
      features: [
        {
          $type: "app.bsky.richtext.facet#link",
          uri: "https://openai.com/index/understanding-ai-and-learning-outcomes/",
        },
      ],
    },
  ];

  const result = resolveFacetLinks(text, facets);

  assert.ok(result.includes("https://openai.com/index/understanding-ai-and-learning-outcomes/"));
  assert.ok(!result.includes("openai.com/index/unders..."));
});

test("resolveFacetLinks handles multi-byte characters before the facet correctly", () => {
  // "🎉" is 4 UTF-8 bytes but a single JS string element (surrogate pair,
  // 2 UTF-16 code units) - a naive string-index implementation would slice
  // at the wrong position here. Byte offsets computed by hand against the
  // real UTF-8 encoding of "🎉 check this out: ".
  const prefix = "🎉 check this out: ";
  const link = "example.com/foo...";
  const text = prefix + link;
  const byteStart = Buffer.byteLength(prefix, "utf8");
  const byteEnd = byteStart + Buffer.byteLength(link, "utf8");

  const facets = [
    {
      index: { byteStart, byteEnd },
      features: [{ $type: "app.bsky.richtext.facet#link", uri: "https://example.com/foo/full-path" }],
    },
  ];

  assert.equal(resolveFacetLinks(text, facets), "🎉 check this out: https://example.com/foo/full-path");
});

test("resolveFacetLinks does not touch a facet whose visible text is already a complete URL", () => {
  const text = "check out https://example.com/foo for more";
  const byteStart = Buffer.byteLength("check out ", "utf8");
  const byteEnd = byteStart + Buffer.byteLength("https://example.com/foo", "utf8");

  const facets = [
    {
      index: { byteStart, byteEnd },
      features: [{ $type: "app.bsky.richtext.facet#link", uri: "https://example.com/foo?utm_source=app" }],
    },
  ];

  assert.equal(resolveFacetLinks(text, facets), text);
});

test("resolveFacetLinks resolves multiple link facets in one post without corrupting offsets", () => {
  const text = "first... and second...";
  const firstByteStart = 0;
  const firstByteEnd = Buffer.byteLength("first...", "utf8");
  const secondByteStart = Buffer.byteLength("first... and ", "utf8");
  const secondByteEnd = Buffer.byteLength(text, "utf8");

  const facets = [
    {
      index: { byteStart: firstByteStart, byteEnd: firstByteEnd },
      features: [{ $type: "app.bsky.richtext.facet#link", uri: "https://a.example/full" }],
    },
    {
      index: { byteStart: secondByteStart, byteEnd: secondByteEnd },
      features: [{ $type: "app.bsky.richtext.facet#link", uri: "https://b.example/full" }],
    },
  ];

  assert.equal(resolveFacetLinks(text, facets), "https://a.example/full and https://b.example/full");
});

test("resolveFacetLinks only touches the link facet's range when tag/mention facets are also present", () => {
  const text = "#news check example.com/story...";
  const tagByteEnd = Buffer.byteLength("#news", "utf8");
  const linkByteStart = Buffer.byteLength("#news check ", "utf8");
  const linkByteEnd = Buffer.byteLength(text, "utf8");

  const facets = [
    {
      index: { byteStart: 0, byteEnd: tagByteEnd },
      features: [{ $type: "app.bsky.richtext.facet#tag", tag: "news" }],
    },
    {
      index: { byteStart: linkByteStart, byteEnd: linkByteEnd },
      features: [{ $type: "app.bsky.richtext.facet#link", uri: "https://example.com/story/full-title" }],
    },
  ];

  assert.equal(resolveFacetLinks(text, facets), "#news check https://example.com/story/full-title");
});

test("resolveFacetLinks returns the text unchanged when facets is not an array", () => {
  assert.equal(resolveFacetLinks("hello world", undefined), "hello world");
  assert.equal(resolveFacetLinks("hello world", null), "hello world");
});
