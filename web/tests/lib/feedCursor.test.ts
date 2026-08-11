import { afterEach, describe, expect, it, vi } from "vitest";

import { clearCursor, loadCursor, saveCursor } from "../../src/lib/feedCursor";

describe("feedCursor", () => {
  afterEach(() => {
    localStorage.clear();
    vi.useRealTimers();
  });

  it("returns null when nothing is stored", () => {
    expect(loadCursor(null)).toBeNull();
  });

  it("round-trips a saved cursor", () => {
    saveCursor(null, "abc123");
    expect(loadCursor(null)).toBe("abc123");
  });

  it("clears the stored cursor", () => {
    saveCursor(null, "abc123");
    clearCursor(null);
    expect(loadCursor(null)).toBeNull();
  });

  it("saving null clears any stored cursor", () => {
    saveCursor(null, "abc123");
    saveCursor(null, null);
    expect(loadCursor(null)).toBeNull();
  });

  it("expires a cursor older than the resume window", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-11T12:00:00Z"));
    saveCursor(null, "abc123");

    vi.setSystemTime(new Date("2026-08-11T15:00:01Z")); // just past 3h
    expect(loadCursor(null)).toBeNull();
  });

  it("keeps a cursor still within the resume window", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-11T12:00:00Z"));
    saveCursor(null, "abc123");

    vi.setSystemTime(new Date("2026-08-11T14:59:00Z")); // just under 3h
    expect(loadCursor(null)).toBe("abc123");
  });

  it("treats malformed stored data as absent", () => {
    localStorage.setItem("goodgorithm:feedCursor:all", "not json");
    expect(loadCursor(null)).toBeNull();
  });

  it("keeps separate categories' cursors independent", () => {
    saveCursor("technology", "tech-cursor");
    saveCursor("animals", "animals-cursor");
    saveCursor(null, "all-cursor");

    expect(loadCursor("technology")).toBe("tech-cursor");
    expect(loadCursor("animals")).toBe("animals-cursor");
    expect(loadCursor(null)).toBe("all-cursor");
  });

  it("clearing one category's cursor doesn't touch another's", () => {
    saveCursor("technology", "tech-cursor");
    saveCursor("animals", "animals-cursor");

    clearCursor("technology");

    expect(loadCursor("technology")).toBeNull();
    expect(loadCursor("animals")).toBe("animals-cursor");
  });
});
