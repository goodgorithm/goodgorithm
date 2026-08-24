import assert from "node:assert/strict";
import { test } from "node:test";

import { withTimeout } from "../src/db";

// Direct unit tests of the timeout mechanism itself, independent of a real
// (or even mocked) database -- a fake never-resolving promise exercises the
// same race checkDatabaseConnection/fetchFeed both rely on, without needing
// a live/slow Postgres query to actually trigger it.

test("withTimeout resolves normally when the promise settles before the deadline", async () => {
  const result = await withTimeout(Promise.resolve("done"), 100, "should not fire");
  assert.equal(result, "done");
});

test("withTimeout rejects with the given message when the promise never settles in time", async () => {
  const neverResolves = new Promise(() => {});
  await assert.rejects(() => withTimeout(neverResolves, 10, "timed out"), /timed out/);
});

test("withTimeout propagates the original rejection when the promise fails before the deadline", async () => {
  const failsFast = Promise.reject(new Error("real failure"));
  await assert.rejects(() => withTimeout(failsFast, 100, "should not fire"), /real failure/);
});
