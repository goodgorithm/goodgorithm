import { afterEach, describe, expect, it, vi } from "vitest";

import { clearCursor, loadCursor, loadSeenIds, saveCursor } from "../../src/lib/feedCursor";

describe("feedCursor", () => {
  afterEach(() => {
    localStorage.clear();
    vi.useRealTimers();
  });

  it("returns null when nothing is stored", () => {
    expect(loadCursor()).toBeNull();
  });

  it("round-trips a saved cursor", () => {
    saveCursor("abc123");
    expect(loadCursor()).toBe("abc123");
  });

  it("clears the stored cursor", () => {
    saveCursor("abc123");
    clearCursor();
    expect(loadCursor()).toBeNull();
  });

  it("saving null clears any stored cursor", () => {
    saveCursor("abc123");
    saveCursor(null);
    expect(loadCursor()).toBeNull();
  });

  it("expires a cursor older than the resume window", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-11T12:00:00Z"));
    saveCursor("abc123");

    vi.setSystemTime(new Date("2026-08-11T15:00:01Z")); // just past 3h
    expect(loadCursor()).toBeNull();
  });

  it("keeps a cursor still within the resume window", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-11T12:00:00Z"));
    saveCursor("abc123");

    vi.setSystemTime(new Date("2026-08-11T14:59:00Z")); // just under 3h
    expect(loadCursor()).toBe("abc123");
  });

  it("treats malformed stored data as absent", () => {
    localStorage.setItem("goodgorithm:feedCursor:all", "not json");
    expect(loadCursor()).toBeNull();
  });

  // --- seen-id list (issue #38) ---

  it("round-trips seen ids alongside the cursor", () => {
    saveCursor("abc123", ["p1", "p2", "p3"]);
    expect(loadCursor()).toBe("abc123");
    expect(loadSeenIds()).toEqual(["p1", "p2", "p3"]);
  });

  it("defaults to no seen ids when none are passed", () => {
    saveCursor("abc123");
    expect(loadSeenIds()).toEqual([]);
  });

  it("returns no seen ids when nothing is stored", () => {
    expect(loadSeenIds()).toEqual([]);
  });

  it("trims seen ids to the cap on save, keeping the most recent", () => {
    const ids = Array.from({ length: 300 }, (_, i) => `id${i}`);
    saveCursor("abc123", ids);

    const stored = loadSeenIds();
    expect(stored).toHaveLength(250);
    expect(stored[0]).toBe("id50");
    expect(stored.at(-1)).toBe("id299");
  });

  it("drops the seen ids when the entry expires", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-11T12:00:00Z"));
    saveCursor("abc123", ["p1"]);

    vi.setSystemTime(new Date("2026-08-11T15:00:01Z")); // just past 3h
    expect(loadSeenIds()).toEqual([]);
  });

  it("drops the seen ids when the cursor is cleared", () => {
    saveCursor("abc123", ["p1"]);
    clearCursor();
    expect(loadSeenIds()).toEqual([]);
  });

  it("drops the seen ids when a null cursor is saved", () => {
    saveCursor("abc123", ["p1"]);
    saveCursor(null, ["p2"]);
    expect(loadSeenIds()).toEqual([]);
  });

  it("treats malformed stored data as no seen ids", () => {
    localStorage.setItem("goodgorithm:feedCursor:all", "not json");
    expect(loadSeenIds()).toEqual([]);
  });

  it("reads an older cursor-only blob as having no seen ids", () => {
    localStorage.setItem(
      "goodgorithm:feedCursor:all",
      JSON.stringify({ cursor: "abc123", savedAt: Date.now() }),
    );
    expect(loadCursor()).toBe("abc123");
    expect(loadSeenIds()).toEqual([]);
  });
});
