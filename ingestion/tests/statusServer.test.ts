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

test("computeStatus is degraded when an instance's most recent poll failed", () => {
  const now = Date.now();
  const mastodon = {
    "failing.example": {
      lastSuccessAt: new Date(now - 60000),
      lastErrorAt: new Date(now),
      lastError: "HTTP 503",
    },
  };
  assert.equal(computeStatus(connected, labelsConnected, mastodon), "degraded");
});

test("computeStatus is ok when an instance failed before but has since recovered", () => {
  const now = Date.now();
  const mastodon = {
    "recovered.example": {
      lastSuccessAt: new Date(now),
      lastErrorAt: new Date(now - 60000),
      lastError: "HTTP 503",
    },
  };
  assert.equal(computeStatus(connected, labelsConnected, mastodon), "ok");
});

test("computeStatus is degraded when an instance has only ever failed, never succeeded", () => {
  const mastodon = {
    "always-failing.example": { lastSuccessAt: null, lastErrorAt: new Date(), lastError: "fetch error" },
  };
  assert.equal(computeStatus(connected, labelsConnected, mastodon), "degraded");
});

test("strictStatusCode maps ok -> 200 and degraded -> 503", () => {
  assert.equal(strictStatusCode("ok"), 200);
  assert.equal(strictStatusCode("degraded"), 503);
});
