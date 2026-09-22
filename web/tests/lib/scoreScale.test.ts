import { describe, expect, it } from "vitest";

import {
  deriveRecency,
  percentileRank,
  QUALITY_THRESHOLD,
  qualityFraction,
  relativeFractions,
} from "../../src/lib/scoreScale";

describe("qualityFraction", () => {
  it("maps the quality-exclude floor to 0", () => {
    expect(qualityFraction(QUALITY_THRESHOLD)).toBe(0);
  });

  it("maps the maximum quality to 1", () => {
    expect(qualityFraction(1)).toBe(1);
  });

  it("maps the midpoint of the realistic range to 0.5", () => {
    const midpoint = (QUALITY_THRESHOLD + 1) / 2;
    expect(qualityFraction(midpoint)).toBeCloseTo(0.5);
  });

  it("clamps values below the quality floor to 0", () => {
    // Shouldn't happen in practice (ranking eligibility already enforces
    // this), but the bar must never render a negative fill if it does.
    expect(qualityFraction(0)).toBe(0);
  });

  it("clamps values above 1 to 1", () => {
    expect(qualityFraction(1.5)).toBe(1);
  });

  it("returns 0 for a null quality (quality-model outage)", () => {
    expect(qualityFraction(null)).toBe(0);
  });
});

describe("deriveRecency", () => {
  it("recovers the decay factor from base / quality", () => {
    expect(deriveRecency({ base: 0.45, rank: 0, quality: 0.9 })).toBeCloseTo(0.5);
  });

  it("clamps to 1 for a fresh post (base == quality)", () => {
    expect(deriveRecency({ base: 0.7, rank: 0, quality: 0.7 })).toBeCloseTo(1);
  });

  it("returns 0 when quality is null (quality-model outage)", () => {
    expect(deriveRecency({ base: 0, rank: 0, quality: null })).toBe(0);
  });

  it("returns 0 when quality is 0 (avoids a divide-by-zero)", () => {
    expect(deriveRecency({ base: 0, rank: 0, quality: 0 })).toBe(0);
  });
});

describe("percentileRank", () => {
  it("ranks the lowest value in a set at its fraction, not 0", () => {
    // 1 of 4 values (itself) is <= the lowest -> 0.25, not "empty"
    expect(percentileRank(1, [1, 2, 3, 4])).toBe(0.25);
  });

  it("ranks the highest value in a set at 1", () => {
    expect(percentileRank(4, [1, 2, 3, 4])).toBe(1);
  });

  it("counts ties as at-or-below", () => {
    expect(percentileRank(2, [1, 2, 2, 2, 5])).toBe(0.8);
  });

  it("returns 1 for a single-value set (nothing to compare against)", () => {
    expect(percentileRank(5, [5])).toBe(1);
  });

  it("returns 0 for an empty comparison set", () => {
    expect(percentileRank(5, [])).toBe(0);
  });
});

describe("relativeFractions", () => {
  function post(id: string, rank: number) {
    return { id, scores: { base: 0.5, rank, quality: 0.5 } } as never;
  }

  it("computes independent percentile ranks for rank", () => {
    const posts = [post("a", 100), post("b", 50), post("c", 200)];

    const result = relativeFractions(posts);

    expect(result.get("a")).toEqual({ rank: 2 / 3 });
    expect(result.get("b")).toEqual({ rank: 1 / 3 });
    expect(result.get("c")).toEqual({ rank: 1 });
  });

  it("gives every post fraction 1 when all values in the batch are equal", () => {
    const posts = [post("a", 1), post("b", 1)];

    const result = relativeFractions(posts);

    expect(result.get("a")).toEqual({ rank: 1 });
    expect(result.get("b")).toEqual({ rank: 1 });
  });

  it("returns an empty map for an empty batch", () => {
    expect(relativeFractions([]).size).toBe(0);
  });
});
