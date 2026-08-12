import { describe, expect, it } from "vitest";

import { POSITIVITY_THRESHOLD, sentimentFraction } from "../../src/lib/scoreRing";

describe("sentimentFraction", () => {
  it("maps the positivity floor to 0", () => {
    expect(sentimentFraction(POSITIVITY_THRESHOLD)).toBe(0);
  });

  it("maps the maximum sentiment to 1", () => {
    expect(sentimentFraction(1)).toBe(1);
  });

  it("maps the midpoint of the realistic range to 0.5", () => {
    const midpoint = (POSITIVITY_THRESHOLD + 1) / 2;
    expect(sentimentFraction(midpoint)).toBeCloseTo(0.5);
  });

  it("clamps values below the positivity floor to 0", () => {
    // Shouldn't happen in practice (ranking eligibility already enforces
    // this), but the ring must never render a negative arc if it does.
    expect(sentimentFraction(-1)).toBe(0);
    expect(sentimentFraction(0)).toBe(0);
  });

  it("clamps values above 1 to 1", () => {
    expect(sentimentFraction(1.5)).toBe(1);
  });
});
