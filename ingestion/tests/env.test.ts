import assert from "node:assert/strict";
import { test } from "node:test";

import { parseNumberEnv } from "../src/env";

test("parseNumberEnv returns the default when the env var is unset", () => {
  delete process.env.TEST_PARSE_NUMBER_ENV;
  assert.equal(parseNumberEnv("TEST_PARSE_NUMBER_ENV", 42), 42);
});

test("parseNumberEnv parses a valid integer string", () => {
  process.env.TEST_PARSE_NUMBER_ENV = "5000";
  assert.equal(parseNumberEnv("TEST_PARSE_NUMBER_ENV", 42), 5000);
  delete process.env.TEST_PARSE_NUMBER_ENV;
});

test("parseNumberEnv parses a valid float string", () => {
  process.env.TEST_PARSE_NUMBER_ENV = "0.045";
  assert.equal(parseNumberEnv("TEST_PARSE_NUMBER_ENV", 1.0), 0.045);
  delete process.env.TEST_PARSE_NUMBER_ENV;
});

test("parseNumberEnv throws on a non-numeric value instead of returning NaN", () => {
  process.env.TEST_PARSE_NUMBER_ENV = "5ooo";
  assert.throws(() => parseNumberEnv("TEST_PARSE_NUMBER_ENV", 42), /Invalid TEST_PARSE_NUMBER_ENV/);
  delete process.env.TEST_PARSE_NUMBER_ENV;
});

test("parseNumberEnv throws on an empty string rather than silently falling back", () => {
  process.env.TEST_PARSE_NUMBER_ENV = "";
  assert.throws(() => parseNumberEnv("TEST_PARSE_NUMBER_ENV", 42), /Invalid TEST_PARSE_NUMBER_ENV/);
  delete process.env.TEST_PARSE_NUMBER_ENV;
});
