import assert from "node:assert/strict";
import { test } from "node:test";

import { buildApp } from "../src/app";

// No live Postgres in this test environment (same as every other test file
// here) - schema validation runs before the handler ever touches the DB, so
// that's what's testable without a real database. Fetching actual rows is
// covered by manual verification against real data (see the categories
// feature's plan/verification notes), not here.

test("/feed rejects an unknown category value (schema validation, before touching the DB)", async () => {
  const app = await buildApp();
  try {
    const res = await app.inject({ method: "GET", url: "/feed?category=not_a_real_category" });
    assert.equal(res.statusCode, 400);
  } finally {
    await app.close();
  }
});

test("/feed accepts a real category value (passes schema validation, fails later only on the unreachable DB)", async () => {
  const app = await buildApp();
  try {
    const res = await app.inject({ method: "GET", url: "/feed?category=technology" });
    // Not 400: proves the category value cleared schema validation. Whatever
    // status follows is the DB-unreachable path, not a validation rejection.
    assert.notEqual(res.statusCode, 400);
  } finally {
    await app.close();
  }
});

test("/feed omitting category behaves exactly as before (no validation error)", async () => {
  const app = await buildApp();
  try {
    const res = await app.inject({ method: "GET", url: "/feed?limit=5" });
    assert.notEqual(res.statusCode, 400);
  } finally {
    await app.close();
  }
});
