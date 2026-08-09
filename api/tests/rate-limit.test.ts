import assert from "node:assert/strict";
import { test } from "node:test";

import { buildApp } from "../src/app";

test("rate limiter allows normal traffic and blocks past the per-IP limit", async () => {
  const app = await buildApp();

  try {
    const first = await app.inject({ method: "GET", url: "/health" });
    assert.equal(first.statusCode, 200);
    assert.equal(first.headers["x-ratelimit-limit"], "100");

    let last = first;
    for (let i = 0; i < 100; i++) {
      last = await app.inject({ method: "GET", url: "/health" });
    }

    assert.equal(last.statusCode, 429);
  } finally {
    await app.close();
  }
});
