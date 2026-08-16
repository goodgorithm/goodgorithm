import assert from "node:assert/strict";
import { test } from "node:test";

import { buildApp, RATE_LIMIT_MAX } from "../src/app";

test("rate limiter allows normal traffic and blocks past the per-IP limit", async () => {
  const app = await buildApp();
  // Rate limiting is a global onRequest hook (see app.ts) applying
  // uniformly to every route - a dependency-free synthetic route here
  // exercises the exact same global behavior as any real one, without
  // coupling this test to /health's DB check (see health.test.ts for
  // that) or hitting Postgres RATE_LIMIT_MAX+1 times.
  app.get("/__test_ping", async () => ({ ok: true }));

  try {
    const first = await app.inject({ method: "GET", url: "/__test_ping" });
    assert.equal(first.statusCode, 200);
    assert.equal(first.headers["x-ratelimit-limit"], String(RATE_LIMIT_MAX));

    let last = first;
    for (let i = 0; i < RATE_LIMIT_MAX; i++) {
      last = await app.inject({ method: "GET", url: "/__test_ping" });
    }

    assert.equal(last.statusCode, 429);
  } finally {
    await app.close();
  }
});
