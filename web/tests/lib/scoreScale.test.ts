import { describe, expect, it } from "vitest";

import {
  percentileRank,
  POSITIVITY_THRESHOLD,
  relativeFractions,
  sentimentFraction,
} from "../../src/lib/scoreScale";

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
    // this), but the bar must never render a negative fill if it does.
    expect(sentimentFraction(-1)).toBe(0);
    expect(sentimentFraction(0)).toBe(0);
  });

  it("clamps values above 1 to 1", () => {
    expect(sentimentFraction(1.5)).toBe(1);
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
  function post(id: string, topicality: number, base: number, rank: number) {
    return { id, scores: { sentiment: 0.5, topicality, base, rank } } as never;
  }

  it("computes independent percentile ranks per metric", () => {
    const posts = [post("a", 1, 10, 100), post("b", 2, 20, 50), post("c", 3, 5, 200)];

    const result = relativeFractions(posts);

    expect(result.get("a")).toEqual({ topicality: 1 / 3, base: 2 / 3, rank: 2 / 3 });
    expect(result.get("b")).toEqual({ topicality: 2 / 3, base: 1, rank: 1 / 3 });
    expect(result.get("c")).toEqual({ topicality: 1, base: 1 / 3, rank: 1 });
  });

  it("gives every post fraction 1 when all values in the batch are equal", () => {
    const posts = [post("a", 1, 1, 1), post("b", 1, 1, 1)];

    const result = relativeFractions(posts);

    expect(result.get("a")).toEqual({ topicality: 1, base: 1, rank: 1 });
    expect(result.get("b")).toEqual({ topicality: 1, base: 1, rank: 1 });
  });

  it("returns an empty map for an empty batch", () => {
    expect(relativeFractions([]).size).toBe(0);
  });
});
