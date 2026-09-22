import assert from "node:assert/strict";
import { test } from "node:test";

import { buildApp } from "../src/app";

// No live Postgres in this test environment (same as every other test file
// here) - schema validation runs before the handler ever touches the DB, so
// that's what's testable without a real database.

test("/v1/feed ignores an unrecognized query param instead of rejecting it", async () => {
  const app = await buildApp();
  try {
    // feedQuerySchema has no `additionalProperties: false`, so a stray
    // param (e.g. a client still sending the removed `category` filter)
    // is just ignored, not a validation error.
    const res = await app.inject({ method: "GET", url: "/v1/feed?category=science_technology" });
    assert.notEqual(res.statusCode, 400);
  } finally {
    await app.close();
  }
});

test("unversioned /feed is gone (404) now that web/'s /v1/feed deploy is confirmed live", async () => {
  const app = await buildApp();
  try {
    const res = await app.inject({ method: "GET", url: "/feed" });
    assert.equal(res.statusCode, 404);
  } finally {
    await app.close();
  }
});
