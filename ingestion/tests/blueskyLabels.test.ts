import assert from "node:assert/strict";
import { test } from "node:test";

import { isExcludedLabel, parsePostTarget } from "../src/blueskyLabels";

test("parsePostTarget extracts did/rkey from a post-collection AT-URI", () => {
  assert.deepEqual(
    parsePostTarget("at://did:plc:nkkjb4ihtvqsp3u5wudunb6x/app.bsky.feed.post/3msqbfmqbdp2a"),
    { did: "did:plc:nkkjb4ihtvqsp3u5wudunb6x", rkey: "3msqbfmqbdp2a" },
  );
});

test("parsePostTarget returns null for non-post-collection AT-URIs", () => {
  // e.g. account/profile-level labels, which this filter doesn't act on.
  assert.equal(parsePostTarget("at://did:plc:nkkjb4ihtvqsp3u5wudunb6x/app.bsky.actor.profile/self"), null);
});

test("parsePostTarget returns null for malformed URIs", () => {
  assert.equal(parsePostTarget("not-a-uri"), null);
  assert.equal(parsePostTarget("at://did:plc:x/app.bsky.feed.post"), null);
  assert.equal(parsePostTarget("at://"), null);
  assert.equal(parsePostTarget(""), null);
});

test("isExcludedLabel matches confirmed adult-content label values", () => {
  assert.equal(
    isExcludedLabel({ src: "did:plc:mod", uri: "at://x/app.bsky.feed.post/y", val: "sexual", cts: "" }),
    true,
  );
  assert.equal(
    isExcludedLabel({ src: "did:plc:mod", uri: "at://x/app.bsky.feed.post/y", val: "porn", cts: "" }),
    true,
  );
});

test("isExcludedLabel does not match unlisted label values", () => {
  assert.equal(
    isExcludedLabel({ src: "did:plc:mod", uri: "at://x/app.bsky.feed.post/y", val: "spam", cts: "" }),
    false,
  );
});

test("isExcludedLabel ignores retractions (neg: true), even for a matching value", () => {
  // Deliberate: once excluded, stays excluded -- there's nothing to "undo"
  // once the matching raw_posts row is already gone. See module comment.
  assert.equal(
    isExcludedLabel({
      src: "did:plc:mod",
      uri: "at://x/app.bsky.feed.post/y",
      val: "sexual",
      neg: true,
      cts: "",
    }),
    false,
  );
});
