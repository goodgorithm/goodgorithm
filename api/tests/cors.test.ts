import assert from "node:assert/strict";
import { test } from "node:test";

import { buildApp } from "../src/app";

// app.ts registers @fastify/cors with `origin: true` (reflect any origin) --
// deliberately, because the native Android/iOS app's WebView origin is
// `https://localhost` / `capacitor://localhost`, not goodgorithm.com. This
// guards against that being tightened to a fixed allowlist that would break
// the shipped app while the website keeps working. See issue #123.

const NATIVE_ORIGINS = ["https://localhost", "capacitor://localhost"];

for (const origin of NATIVE_ORIGINS) {
  test(`CORS: OPTIONS preflight from ${origin} is allowed`, async () => {
    const app = await buildApp();
    try {
      const res = await app.inject({
        method: "OPTIONS",
        url: "/v1/feed",
        headers: { origin, "access-control-request-method": "GET" },
      });
      // @fastify/cors short-circuits the preflight before the route/DB.
      assert.equal(res.statusCode, 204);
      assert.equal(res.headers["access-control-allow-origin"], origin);
    } finally {
      await app.close();
    }
  });

  test(`CORS: GET /v1/feed reflects the ${origin} origin regardless of the downstream status`, async () => {
    const app = await buildApp();
    try {
      const res = await app.inject({ method: "GET", url: "/v1/feed?limit=1", headers: { origin } });
      // The CORS hook runs on every response, including the DB-unreachable
      // error path this test hits (no live Postgres) -- the header must be
      // there whatever the status code is.
      assert.equal(res.headers["access-control-allow-origin"], origin);
    } finally {
      await app.close();
    }
  });
}
