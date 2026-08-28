import assert from "node:assert/strict";
import { test } from "node:test";

import { computeStatus, strictStatusCode } from "../src/statusServer";

const connected = { connected: true };
const disconnected = { connected: false };
const labelsConnected = { connected: true, disabled: false };
const labelsDisconnected = { connected: false, disabled: false };
const labelsDisabled = { connected: false, disabled: true };

test("computeStatus is ok when everything is connected and no instance has failed", () => {
  const mastodon = {
    "a.example": { lastSuccessAt: new Date(), lastErrorAt: null, lastError: null },
  };
  assert.equal(computeStatus(connected, labelsConnected, mastodon), "ok");
});

test("computeStatus is degraded when the Bluesky firehose is disconnected", () => {
  assert.equal(computeStatus(disconnected, labelsConnected, {}), "degraded");
});

test("computeStatus is degraded when the labels stream is disconnected and not intentionally disabled", () => {
  assert.equal(computeStatus(connected, labelsDisconnected, {}), "degraded");
});

test("computeStatus is ok when the labels stream is disconnected but intentionally disabled", () => {
  assert.equal(computeStatus(connected, labelsDisabled, {}), "ok");
});

test("computeStatus is ok for an instance that has never been polled yet", () => {
  const mastodon = {
    "never-polled.example": { lastSuccessAt: null, lastErrorAt: null, lastError: null },
  };
  assert.equal(computeStatus(connected, labelsConnected, mastodon), "ok");
});

const now = Date.now();
const healthy = { lastSuccessAt: new Date(now), lastErrorAt: null, lastError: null };
const erroring = { lastSuccessAt: new Date(now - 60000), lastErrorAt: new Date(now), lastError: "HTTP 503" };
const recovered = { lastSuccessAt: new Date(now), lastErrorAt: new Date(now - 60000), lastError: "HTTP 503" };
const neverSucceeded = { lastSuccessAt: null, lastErrorAt: new Date(now), lastError: "fetch error" };

test("computeStatus stays ok when only a minority of Mastodon instances are erroring (issue #125)", () => {
  const mastodon = { a: healthy, b: healthy, c: erroring, d: neverSucceeded };
  assert.equal(computeStatus(connected, labelsConnected, mastodon), "ok");
});

test("computeStatus is degraded when EVERY polled Mastodon instance is erroring (systemic)", () => {
  const mastodon = { a: erroring, b: erroring, c: neverSucceeded };
  assert.equal(computeStatus(connected, labelsConnected, mastodon), "degraded");
});

test("computeStatus is ok when instances failed before but have all since recovered", () => {
  const mastodon = { a: recovered, b: recovered, c: healthy };
  assert.equal(computeStatus(connected, labelsConnected, mastodon), "ok");
});

test("computeStatus honours a lower MASTODON_DEGRADED_ERROR_RATIO (majority)", () => {
  const mastodon = { a: erroring, b: erroring, c: erroring, d: healthy }; // 3/4 erroring
  assert.equal(computeStatus(connected, labelsConnected, mastodon, 1), "ok");
  assert.equal(computeStatus(connected, labelsConnected, mastodon, 0.5), "degraded");
});

test("strictStatusCode maps ok -> 200 and degraded -> 503", () => {
  assert.equal(strictStatusCode("ok"), 200);
  assert.equal(strictStatusCode("degraded"), 503);
});
