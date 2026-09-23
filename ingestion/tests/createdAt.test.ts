import assert from "node:assert/strict";
import { test } from "node:test";

import { capCreatedAt } from "../src/createdAt";

const observed = new Date("2026-09-23T06:00:00.000Z");

test("capCreatedAt keeps a declared time earlier than the observed time", () => {
  assert.deepEqual(capCreatedAt("2026-09-23T05:59:30.000Z", observed), new Date("2026-09-23T05:59:30.000Z"));
});

test("capCreatedAt keeps a backdated declared time", () => {
  assert.deepEqual(capCreatedAt("2019-01-01T00:00:00.000Z", observed), new Date("2019-01-01T00:00:00.000Z"));
});

test("capCreatedAt caps a slightly-future declared time at the observed time, with no grace window", () => {
  assert.deepEqual(capCreatedAt("2026-09-23T06:00:30.000Z", observed), observed);
});

test("capCreatedAt caps a far-future declared time at the observed time", () => {
  assert.deepEqual(capCreatedAt("5085-08-25T11:55:59.558Z", observed), observed);
});

test("capCreatedAt falls back to the observed time for a missing declared time", () => {
  assert.deepEqual(capCreatedAt(undefined, observed), observed);
  assert.deepEqual(capCreatedAt(null, observed), observed);
  assert.deepEqual(capCreatedAt("", observed), observed);
});

test("capCreatedAt falls back to the observed time for an unparseable declared time", () => {
  assert.deepEqual(capCreatedAt("not a date", observed), observed);
});
