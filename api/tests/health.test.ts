import assert from "node:assert/strict";
import { test } from "node:test";

import { buildApp } from "../src/app";

// No live Postgres in this test environment (same as every other test file
// here - db.ts's postgres() client is lazy, doesn't need a real DATABASE_URL
// at import time) - so this exercises the real "DB unreachable" path, not a
// mocked one. A health check that only ever reports healthy is worse than
// no health check at all, since it creates false confidence for whatever's
// watching it.
test("/health reports unhealthy (503) when the database is unreachable", async () => {
  const app = await buildApp();
  try {
    const res = await app.inject({ method: "GET", url: "/health" });
    assert.equal(res.statusCode, 503);
    const body = JSON.parse(res.body);
    assert.equal(body.status, "error");
    assert.equal(body.database, "unreachable");
    // "unknown" outside Railway (RAILWAY_GIT_COMMIT_SHA unset in this test
    // environment) - just confirming the field exists, not a specific value.
    assert.equal(typeof body.version, "string");
  } finally {
    await app.close();
  }
});
