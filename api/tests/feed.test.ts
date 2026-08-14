import assert from "node:assert/strict";
import { test } from "node:test";

import { buildApp } from "../src/app";

// No live Postgres in this test environment (same as every other test file
// here) - schema validation runs before the handler ever touches the DB, so
// that's what's testable without a real database. Fetching actual rows is
// covered by manual verification against real data (see the categories
// feature's plan/verification notes), not here.
//
// Both /v1/feed (the real path going forward) and the unprefixed /feed
// (kept temporarily so api/'s and web/'s independent, non-atomic deploys
// can't 404 each other - see app.ts and CLAUDE.md's Versioning &
// migration section) are exercised identically, since they're meant to
// behave identically until /feed is dropped.

for (const path of ["/v1/feed", "/feed"]) {
  test(`${path} rejects an unknown category value (schema validation, before touching the DB)`, async () => {
    const app = await buildApp();
    try {
      const res = await app.inject({ method: "GET", url: `${path}?category=not_a_real_category` });
      assert.equal(res.statusCode, 400);
    } finally {
      await app.close();
    }
  });

  test(`${path} accepts a real category value (passes schema validation, fails later only on the unreachable DB)`, async () => {
    const app = await buildApp();
    try {
      const res = await app.inject({ method: "GET", url: `${path}?category=science_technology` });
      // Not 400: proves the category value cleared schema validation. Whatever
      // status follows is the DB-unreachable path, not a validation rejection.
      assert.notEqual(res.statusCode, 400);
    } finally {
      await app.close();
    }
  });

  test(`${path} omitting category behaves exactly as before (no validation error)`, async () => {
    const app = await buildApp();
    try {
      const res = await app.inject({ method: "GET", url: `${path}?limit=5` });
      assert.notEqual(res.statusCode, 400);
    } finally {
      await app.close();
    }
  });
}
