import assert from "node:assert/strict";
import { test } from "node:test";

import { buildApp } from "../src/app";

test("API routes fail closed (500) when LABELING_ACCESS_TOKEN isn't configured", async () => {
  delete process.env.LABELING_ACCESS_TOKEN;
  const app = await buildApp();
  try {
    const res = await app.inject({ method: "GET", url: "/api/studies" });
    assert.equal(res.statusCode, 500);
  } finally {
    await app.close();
  }
});

test("API routes reject a missing/wrong access token with 401", async () => {
  process.env.LABELING_ACCESS_TOKEN = "test-token";
  const app = await buildApp();
  try {
    const noToken = await app.inject({ method: "GET", url: "/api/studies" });
    assert.equal(noToken.statusCode, 401);

    const wrongToken = await app.inject({
      method: "GET",
      url: "/api/studies",
      headers: { "x-access-token": "wrong" },
    });
    assert.equal(wrongToken.statusCode, 401);
  } finally {
    await app.close();
    delete process.env.LABELING_ACCESS_TOKEN;
  }
});

test("the review UI itself does not require the access token (only the API does)", async () => {
  const app = await buildApp();
  try {
    const res = await app.inject({ method: "GET", url: "/" });
    assert.equal(res.statusCode, 200);
    assert.match(res.headers["content-type"] as string, /text\/html/);
  } finally {
    await app.close();
  }
});
