import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScoreDetails } from "../../src/components/ScoreDetails";

const scores = { sentiment: 0.65, topicality: 1.2, base: 0.72, rank: 0.42, quality: 0.8 };
const relative = { rank: 0.1 };

describe("ScoreDetails", () => {
  it("shows a bar and label at a glance, collapsed by default", () => {
    render(<ScoreDetails scores={scores} relative={relative} />);

    expect(screen.getByText("Scores")).toBeInTheDocument();
  });

  it("puts the exact numbers in a hover tooltip", () => {
    render(<ScoreDetails scores={scores} relative={relative} />);

    const summary = screen.getByText("Scores").closest("summary");
    expect(summary).toHaveAttribute("title", "Quality 0.80 · Recency 0.90 · Rank 0.42");
  });

  it("shows quality, recency, and rank, each with its own bar, when expanded", () => {
    render(<ScoreDetails scores={scores} relative={relative} />);

    expect(screen.getByText("Quality")).toBeInTheDocument();
    expect(screen.getByText("Recency")).toBeInTheDocument();
    expect(screen.getByText("Rank")).toBeInTheDocument();
    expect(screen.getByText("0.80")).toBeInTheDocument();
    expect(screen.getByText("0.90")).toBeInTheDocument();
    expect(screen.getByText("0.42")).toBeInTheDocument();
  });

  it("labels only rank as batch-relative, not absolute", () => {
    render(<ScoreDetails scores={scores} relative={relative} />);

    expect(screen.getAllByText("vs. this batch")).toHaveLength(1);
  });

  it("shows a dash, not NaN, when quality is null (quality-model outage)", () => {
    const outageScores = { ...scores, quality: null };
    render(<ScoreDetails scores={outageScores} relative={relative} />);

    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("links externally to the Wiki's Algorithm page for the full explanation (issue #31)", () => {
    render(<ScoreDetails scores={scores} relative={relative} />);

    const link = screen.getByRole("link", { name: /how these are calculated/i });
    expect(link).toHaveAttribute("href", "https://github.com/goodgorithm/goodgorithm/wiki/Algorithm");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
  });
});
