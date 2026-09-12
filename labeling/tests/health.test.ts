import assert from "node:assert/strict";
import { test } from "node:test";

import { buildApp } from "../src/app";

// No live Postgres in this test environment (same as api/'s equivalent test
// - db.ts's postgres() client is lazy, doesn't need a real DATABASE_URL at
// import time) - exercises the real "DB unreachable" path.
test("/health reports unhealthy (503) when the database is unreachable", async () => {
  const app = await buildApp();
  try {
    const res = await app.inject({ method: "GET", url: "/health" });
    assert.equal(res.statusCode, 503);
    const body = JSON.parse(res.body);
    assert.equal(body.status, "error");
    assert.equal(body.database.reachable, false);
    assert.equal(typeof body.database.error, "string");
  } finally {
    await app.close();
  }
});

test("/health does not require the access token", async () => {
  const app = await buildApp();
  try {
    const res = await app.inject({ method: "GET", url: "/health" });
    // 503 (DB unreachable), not 401/500 (access-token gate) - health is
    // deliberately outside that hook, see app.ts.
    assert.notEqual(res.statusCode, 401);
  } finally {
    await app.close();
  }
});
