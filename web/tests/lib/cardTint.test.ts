import { describe, expect, it } from "vitest";

import { cardTintVar } from "../../src/lib/cardTint";

describe("cardTintVar", () => {
  it("is stable for a given id", () => {
    const id = "at://did:plc:abc123/app.bsky.feed.post/xyz";
    expect(cardTintVar(id)).toBe(cardTintVar(id));
  });

  it("only ever returns one of the five tint vars", () => {
    const allowed = new Set([1, 2, 3, 4, 5].map((n) => `var(--card-tint-${n})`));
    for (let i = 0; i < 500; i++) {
      expect(allowed.has(cardTintVar(`post-${i}`))).toBe(true);
    }
  });

  it("spreads ids across all five buckets", () => {
    const seen = new Set<string>();
    for (let i = 0; i < 500; i++) {
      seen.add(cardTintVar(`post-${i}`));
    }
    expect(seen.size).toBe(5);
  });

  it("handles an empty id without throwing", () => {
    expect(cardTintVar("")).toMatch(/^var\(--card-tint-[1-5]\)$/);
  });
});
