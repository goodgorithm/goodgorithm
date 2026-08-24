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
    assert.equal(body.database.reachable, false);
    // The real error (connection-refused, in this no-live-DB test
    // environment) is no longer discarded -- previously a bare `catch {}`.
    assert.equal(typeof body.database.error, "string");
    assert.equal(typeof body.database.latency_ms, "number");
    // "unknown" outside Railway (RAILWAY_GIT_COMMIT_SHA unset in this test
    // environment) - just confirming the field exists, not a specific value.
    assert.equal(typeof body.version, "string");
    assert.equal(typeof body.timestamp, "string");
  } finally {
    await app.close();
  }
});

test("/health's config block is present regardless of database reachability", async () => {
  // Public, safe-to-expose config values don't depend on DB reachability --
  // testable here without a live/mocked DB, since the unreachable path
  // above fires reliably in this test environment.
  const app = await buildApp();
  try {
    const res = await app.inject({ method: "GET", url: "/health" });
    const body = JSON.parse(res.body);
    assert.equal(typeof body.config.rate_limit_max, "number");
    assert.equal(typeof body.config.rate_limit_time_window, "string");
    assert.equal(typeof body.config.feed_limit_max, "number");
    assert.equal(typeof body.config.feed_limit_default, "number");
    assert.equal(typeof body.config.db_pool_max_size, "number");
    assert.equal(typeof body.config.health_check_timeout_ms, "number");
    assert.equal(typeof body.config.feed_query_timeout_ms, "number");
  } finally {
    await app.close();
  }
});
