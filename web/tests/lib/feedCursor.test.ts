import { afterEach, describe, expect, it, vi } from "vitest";

import { clearCursor, loadCursor, saveCursor } from "../../src/lib/feedCursor";

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

  it("keeps separate categories' cursors independent", () => {
    saveCursor("science_technology", "tech-cursor");
    saveCursor("diaries_daily_life", "diaries_daily_life-cursor");

    expect(loadCursor("science_technology")).toBe("tech-cursor");
    expect(loadCursor("diaries_daily_life")).toBe("diaries_daily_life-cursor");
  });

  it("clearing one category's cursor doesn't touch another's", () => {
    saveCursor("science_technology", "tech-cursor");
    saveCursor("diaries_daily_life", "diaries_daily_life-cursor");

    clearCursor("science_technology");

    expect(loadCursor("science_technology")).toBeNull();
    expect(loadCursor("diaries_daily_life")).toBe("diaries_daily_life-cursor");
  });
});
