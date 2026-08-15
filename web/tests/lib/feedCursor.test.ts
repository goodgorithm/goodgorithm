import { afterEach, describe, expect, it, vi } from "vitest";

import { clearCursor, loadCursor, saveCursor } from "../../src/lib/feedCursor";

describe("feedCursor", () => {
  afterEach(() => {
    localStorage.clear();
    vi.useRealTimers();
  });

  it("returns null when nothing is stored", () => {
    expect(loadCursor("gaming")).toBeNull();
  });

  it("round-trips a saved cursor", () => {
    saveCursor("gaming", "abc123");
    expect(loadCursor("gaming")).toBe("abc123");
  });

  it("clears the stored cursor", () => {
    saveCursor("gaming", "abc123");
    clearCursor("gaming");
    expect(loadCursor("gaming")).toBeNull();
  });

  it("saving null clears any stored cursor", () => {
    saveCursor("gaming", "abc123");
    saveCursor("gaming", null);
    expect(loadCursor("gaming")).toBeNull();
  });

  it("expires a cursor older than the resume window", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-11T12:00:00Z"));
    saveCursor("gaming", "abc123");

    vi.setSystemTime(new Date("2026-08-11T15:00:01Z")); // just past 3h
    expect(loadCursor("gaming")).toBeNull();
  });

  it("keeps a cursor still within the resume window", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-11T12:00:00Z"));
    saveCursor("gaming", "abc123");

    vi.setSystemTime(new Date("2026-08-11T14:59:00Z")); // just under 3h
    expect(loadCursor("gaming")).toBe("abc123");
  });

  it("treats malformed stored data as absent", () => {
    localStorage.setItem("goodgorithm:feedCursor:gaming", "not json");
    expect(loadCursor("gaming")).toBeNull();
  });

  it("keeps separate categories' cursors independent", () => {
    saveCursor("science_technology", "tech-cursor");
    saveCursor("gaming", "gaming-cursor");

    expect(loadCursor("science_technology")).toBe("tech-cursor");
    expect(loadCursor("gaming")).toBe("gaming-cursor");
  });

  it("clearing one category's cursor doesn't touch another's", () => {
    saveCursor("science_technology", "tech-cursor");
    saveCursor("gaming", "gaming-cursor");

    clearCursor("science_technology");

    expect(loadCursor("science_technology")).toBeNull();
    expect(loadCursor("gaming")).toBe("gaming-cursor");
  });
});
