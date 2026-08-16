import assert from "node:assert/strict";
import { test } from "node:test";

import { checkAndPing, recordInsert } from "../src/heartbeat";

test("checkAndPing does not fetch when nothing was inserted since the last check", async () => {
  const calls: string[] = [];
  const originalFetch = global.fetch;
  global.fetch = (async (url: string) => {
    calls.push(url);
    return new Response();
  }) as typeof fetch;

  try {
    await checkAndPing("https://example.com/ping");
    assert.deepEqual(calls, []);
  } finally {
    global.fetch = originalFetch;
  }
});

test("checkAndPing fetches once inserts have happened, then resets the counter", async () => {
  const calls: string[] = [];
  const originalFetch = global.fetch;
  global.fetch = (async (url: string) => {
    calls.push(url);
    return new Response();
  }) as typeof fetch;

  try {
    recordInsert();
    recordInsert();
    await checkAndPing("https://example.com/ping");
    assert.deepEqual(calls, ["https://example.com/ping"]);

    // Second call with no new inserts in between should not fetch again.
    await checkAndPing("https://example.com/ping");
    assert.deepEqual(calls, ["https://example.com/ping"]);
  } finally {
    global.fetch = originalFetch;
  }
});

test("checkAndPing does not throw when the ping request itself fails", async () => {
  const originalFetch = global.fetch;
  global.fetch = (async () => {
    throw new Error("network unreachable");
  }) as typeof fetch;

  try {
    recordInsert();
    await assert.doesNotReject(() => checkAndPing("https://example.com/ping"));
  } finally {
    global.fetch = originalFetch;
  }
});
