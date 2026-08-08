import assert from "node:assert/strict";
import { test } from "node:test";

import { decodeCursor, encodeCursor } from "../src/pagination";

test("encodeCursor/decodeCursor roundtrip", () => {
  const cursor = { rank_score: 4.49, id: "5b6b6b26-2f7e-4b1a-9d1a-000000000000" };
  const encoded = encodeCursor(cursor);
  const decoded = decodeCursor(encoded);
  assert.deepEqual(decoded, cursor);
});

test("encodeCursor produces an opaque, url-safe string", () => {
  const encoded = encodeCursor({ rank_score: 1.23, id: "abc" });
  assert.match(encoded, /^[A-Za-z0-9_-]+$/);
});

test("decodeCursor rejects malformed base64/JSON", () => {
  assert.throws(() => decodeCursor("not-valid-base64!!!"), /invalid cursor/);
});

test("decodeCursor rejects valid JSON with the wrong shape", () => {
  const badCursor = Buffer.from(JSON.stringify({ foo: "bar" }), "utf8").toString("base64url");
  assert.throws(() => decodeCursor(badCursor), /invalid cursor/);
});

test("decodeCursor rejects wrong field types", () => {
  const badCursor = Buffer.from(
    JSON.stringify({ rank_score: "not-a-number", id: "abc" }),
    "utf8",
  ).toString("base64url");
  assert.throws(() => decodeCursor(badCursor), /invalid cursor/);
});
