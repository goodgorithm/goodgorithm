import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScoreDetails } from "../../src/components/ScoreDetails";

const scores = { sentiment: 0.65, topicality: 1.2, base: 0.8, rank: 0.42 };
const relative = { topicality: 0.9, base: 0.5, rank: 0.1 };

describe("ScoreDetails", () => {
  it("shows a bar and label at a glance, collapsed by default", () => {
    render(<ScoreDetails scores={scores} relative={relative} />);

    expect(screen.getByText("Scores")).toBeInTheDocument();
  });

  it("puts the exact numbers in a hover tooltip", () => {
    render(<ScoreDetails scores={scores} relative={relative} />);

    const summary = screen.getByText("Scores").closest("summary");
    expect(summary).toHaveAttribute(
      "title",
      "Sentiment 0.65 · Topicality 1.20 · Base 0.80 · Rank 0.42",
    );
  });

  it("shows all four scores, each with its own bar, when expanded", () => {
    render(<ScoreDetails scores={scores} relative={relative} />);

    expect(screen.getByText("Sentiment")).toBeInTheDocument();
    expect(screen.getByText("Topicality")).toBeInTheDocument();
    expect(screen.getByText("Base")).toBeInTheDocument();
    expect(screen.getByText("Rank")).toBeInTheDocument();
    expect(screen.getByText("0.65")).toBeInTheDocument();
    expect(screen.getByText("1.20")).toBeInTheDocument();
    expect(screen.getByText("0.80")).toBeInTheDocument();
    expect(screen.getByText("0.42")).toBeInTheDocument();
  });

  it("labels the relative scores as batch-relative, not absolute", () => {
    render(<ScoreDetails scores={scores} relative={relative} />);

    expect(screen.getAllByText("vs. this batch")).toHaveLength(3);
  });

  it("links externally to the Wiki's Algorithm page for the full explanation (issue #31)", () => {
    render(<ScoreDetails scores={scores} relative={relative} />);

    const link = screen.getByRole("link", { name: /how these are calculated/i });
    expect(link).toHaveAttribute("href", "https://github.com/goodgorithm/goodgorithm/wiki/Algorithm");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
  });
});
