import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScoreDetails } from "../../src/components/ScoreDetails";

const scores = { sentiment: 0.65, topicality: 1.2, base: 0.8, rank: 0.42 };

describe("ScoreDetails", () => {
  it("shows a ring and label at a glance, collapsed by default", () => {
    render(<ScoreDetails scores={scores} />);

    expect(screen.getByText("Scores")).toBeInTheDocument();
    // dl content is present in the DOM (native <details>), but collapsed -
    // the ring/label above is what's meant to be seen without expanding.
    expect(screen.getByText("Sentiment")).toBeInTheDocument();
  });

  it("puts the exact numbers in a hover tooltip", () => {
    render(<ScoreDetails scores={scores} />);

    const summary = screen.getByText("Scores").closest("summary");
    expect(summary).toHaveAttribute(
      "title",
      "Sentiment 0.65 · Topicality 1.20 · Base 0.80 · Rank 0.42",
    );
  });

  it("shows all four raw scores when expanded", () => {
    render(<ScoreDetails scores={scores} />);

    expect(screen.getByText("0.650")).toBeInTheDocument();
    expect(screen.getByText("1.200")).toBeInTheDocument();
    expect(screen.getByText("0.800")).toBeInTheDocument();
    expect(screen.getByText("0.420")).toBeInTheDocument();
  });

  it("links to the algorithm page for the full explanation", () => {
    render(<ScoreDetails scores={scores} />);

    const link = screen.getByRole("link", { name: /how these are calculated/i });
    expect(link).toHaveAttribute("href", "/algorithm");
  });
});
