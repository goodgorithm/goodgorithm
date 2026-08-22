import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import {
  _clearPendingExclusionsForTests,
  consumePendingExclusion,
  markPendingExclusion,
  pendingExclusionCount,
} from "../src/pendingExclusions";

// Module-level singleton state -- unlike this directory's other pure-
// function tests, isolation between cases needs an explicit reset.
beforeEach(() => {
  _clearPendingExclusionsForTests();
});

test("consumePendingExclusion returns true right after marking", () => {
  markPendingExclusion("did:plc:x/abc", 0);
  assert.equal(consumePendingExclusion("did:plc:x/abc", 10), true);
});

test("consumePendingExclusion returns false for an unknown sourceId", () => {
  assert.equal(consumePendingExclusion("did:plc:never-marked/abc", 0), false);
});

test("consumePendingExclusion is one-shot -- a second call returns false", () => {
  markPendingExclusion("did:plc:x/abc", 0);
  assert.equal(consumePendingExclusion("did:plc:x/abc", 10), true);
  assert.equal(consumePendingExclusion("did:plc:x/abc", 20), false);
});

test("consumePendingExclusion returns false once the TTL has expired", () => {
  markPendingExclusion("did:plc:x/abc", 0); // expires at TTL (default 30000)
  assert.equal(consumePendingExclusion("did:plc:x/abc", 30001), false);
});

test("markPendingExclusion opportunistically sweeps already-expired entries", () => {
  markPendingExclusion("did:plc:a/1", 0); // expires at 30000
  markPendingExclusion("did:plc:b/2", 0); // expires at 30000
  assert.equal(pendingExclusionCount(), 2);

  // Marking a third entry well past the first two's expiry should sweep
  // them, leaving only the new live entry.
  markPendingExclusion("did:plc:c/3", 40000);
  assert.equal(pendingExclusionCount(), 1);
  assert.equal(consumePendingExclusion("did:plc:a/1", 40000), false);
  assert.equal(consumePendingExclusion("did:plc:c/3", 40000), true);
});
