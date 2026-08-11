import { afterEach, describe, expect, it, vi } from "vitest";

import { clearCursor, loadCursor, saveCursor } from "../../src/lib/feedCursor";

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
    localStorage.setItem("goodgorithm:feedCursor", "not json");
    expect(loadCursor()).toBeNull();
  });
});
