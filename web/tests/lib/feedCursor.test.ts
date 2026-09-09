import { afterEach, describe, expect, it, vi } from "vitest";

import { clearCursor, loadCursor, loadSeenIds, saveCursor } from "../../src/lib/feedCursor";

describe("feedCursor", () => {
  afterEach(() => {
    localStorage.clear();
    vi.useRealTimers();
  });

  it("returns null when nothing is stored", () => {
    expect(loadCursor("diaries_daily_life")).toBeNull();
  });

  it("round-trips a saved cursor", () => {
    saveCursor("diaries_daily_life", "abc123");
    expect(loadCursor("diaries_daily_life")).toBe("abc123");
  });

  it("clears the stored cursor", () => {
    saveCursor("diaries_daily_life", "abc123");
    clearCursor("diaries_daily_life");
    expect(loadCursor("diaries_daily_life")).toBeNull();
  });

  it("saving null clears any stored cursor", () => {
    saveCursor("diaries_daily_life", "abc123");
    saveCursor("diaries_daily_life", null);
    expect(loadCursor("diaries_daily_life")).toBeNull();
  });

  it("expires a cursor older than the resume window", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-11T12:00:00Z"));
    saveCursor("diaries_daily_life", "abc123");

    vi.setSystemTime(new Date("2026-08-11T15:00:01Z")); // just past 3h
    expect(loadCursor("diaries_daily_life")).toBeNull();
  });

  it("keeps a cursor still within the resume window", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-11T12:00:00Z"));
    saveCursor("diaries_daily_life", "abc123");

    vi.setSystemTime(new Date("2026-08-11T14:59:00Z")); // just under 3h
    expect(loadCursor("diaries_daily_life")).toBe("abc123");
  });

  it("treats malformed stored data as absent", () => {
    localStorage.setItem("goodgorithm:feedCursor:diaries_daily_life", "not json");
    expect(loadCursor("diaries_daily_life")).toBeNull();
  });

  // null (the unfiltered feed, issue #101) round-trips through its own
  // "all" storage key, same as any real category.
  it("round-trips a saved cursor for the unfiltered feed (null category)", () => {
    saveCursor(null, "all-cursor");
    expect(loadCursor(null)).toBe("all-cursor");
  });

  it("clears the unfiltered feed's stored cursor", () => {
    saveCursor(null, "all-cursor");
    clearCursor(null);
    expect(loadCursor(null)).toBeNull();
  });

  it("keeps separate categories' cursors independent", () => {
    saveCursor("science_technology", "tech-cursor");
    saveCursor("diaries_daily_life", "diaries_daily_life-cursor");
    saveCursor(null, "all-cursor");

    expect(loadCursor("science_technology")).toBe("tech-cursor");
    expect(loadCursor("diaries_daily_life")).toBe("diaries_daily_life-cursor");
    expect(loadCursor(null)).toBe("all-cursor");
  });

  it("clearing one category's cursor doesn't touch another's", () => {
    saveCursor("science_technology", "tech-cursor");
    saveCursor("diaries_daily_life", "diaries_daily_life-cursor");

    clearCursor("science_technology");

    expect(loadCursor("science_technology")).toBeNull();
    expect(loadCursor("diaries_daily_life")).toBe("diaries_daily_life-cursor");
  });

  // --- seen-id list (issue #38) ---

  it("round-trips seen ids alongside the cursor", () => {
    saveCursor("diaries_daily_life", "abc123", ["p1", "p2", "p3"]);
    expect(loadCursor("diaries_daily_life")).toBe("abc123");
    expect(loadSeenIds("diaries_daily_life")).toEqual(["p1", "p2", "p3"]);
  });

  it("defaults to no seen ids when none are passed", () => {
    saveCursor("diaries_daily_life", "abc123");
    expect(loadSeenIds("diaries_daily_life")).toEqual([]);
  });

  it("returns no seen ids when nothing is stored", () => {
    expect(loadSeenIds("diaries_daily_life")).toEqual([]);
  });

  it("trims seen ids to the cap on save, keeping the most recent", () => {
    const ids = Array.from({ length: 300 }, (_, i) => `id${i}`);
    saveCursor("diaries_daily_life", "abc123", ids);

    const stored = loadSeenIds("diaries_daily_life");
    expect(stored).toHaveLength(250);
    expect(stored[0]).toBe("id50");
    expect(stored.at(-1)).toBe("id299");
  });

  it("drops the seen ids when the entry expires", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-11T12:00:00Z"));
    saveCursor("diaries_daily_life", "abc123", ["p1"]);

    vi.setSystemTime(new Date("2026-08-11T15:00:01Z")); // just past 3h
    expect(loadSeenIds("diaries_daily_life")).toEqual([]);
  });

  it("drops the seen ids when the cursor is cleared", () => {
    saveCursor("diaries_daily_life", "abc123", ["p1"]);
    clearCursor("diaries_daily_life");
    expect(loadSeenIds("diaries_daily_life")).toEqual([]);
  });

  it("drops the seen ids when a null cursor is saved", () => {
    saveCursor("diaries_daily_life", "abc123", ["p1"]);
    saveCursor("diaries_daily_life", null, ["p2"]);
    expect(loadSeenIds("diaries_daily_life")).toEqual([]);
  });

  it("treats malformed stored data as no seen ids", () => {
    localStorage.setItem("goodgorithm:feedCursor:diaries_daily_life", "not json");
    expect(loadSeenIds("diaries_daily_life")).toEqual([]);
  });

  it("reads an older cursor-only blob as having no seen ids", () => {
    localStorage.setItem(
      "goodgorithm:feedCursor:diaries_daily_life",
      JSON.stringify({ cursor: "abc123", savedAt: Date.now() }),
    );
    expect(loadCursor("diaries_daily_life")).toBe("abc123");
    expect(loadSeenIds("diaries_daily_life")).toEqual([]);
  });

  it("keeps separate categories' seen ids independent", () => {
    saveCursor("science_technology", "tech-cursor", ["t1"]);
    saveCursor("diaries_daily_life", "diaries-cursor", ["d1", "d2"]);
    saveCursor(null, "all-cursor", ["a1"]);

    expect(loadSeenIds("science_technology")).toEqual(["t1"]);
    expect(loadSeenIds("diaries_daily_life")).toEqual(["d1", "d2"]);
    expect(loadSeenIds(null)).toEqual(["a1"]);
  });
});
