import { describe, expect, it } from "vitest";

import { formatRelativeTime } from "../../src/lib/relativeTime";

describe("formatRelativeTime", () => {
  const now = new Date("2026-08-09T12:00:00Z");

  it("formats minutes ago", () => {
    expect(formatRelativeTime("2026-08-09T11:55:00Z", now)).toBe("5 minutes ago");
  });

  it("formats hours ago", () => {
    expect(formatRelativeTime("2026-08-09T09:00:00Z", now)).toBe("3 hours ago");
  });

  it("formats days ago", () => {
    expect(formatRelativeTime("2026-08-07T12:00:00Z", now)).toBe("2 days ago");
  });
});
