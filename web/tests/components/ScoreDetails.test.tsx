import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ScoreDetails } from "../../src/components/ScoreDetails";

const scores = { sentiment: 0.65, topicality: 1.2, base: 0.8, rank: 0.42 };
const relative = { topicality: 0.9, base: 0.5, rank: 0.1 };
const noop = () => {};

describe("ScoreDetails", () => {
  it("shows a bar and label at a glance, collapsed by default", () => {
    render(<ScoreDetails scores={scores} relative={relative} navigate={noop} />);

    expect(screen.getByText("Scores")).toBeInTheDocument();
  });

  it("puts the exact numbers in a hover tooltip", () => {
    render(<ScoreDetails scores={scores} relative={relative} navigate={noop} />);

    const summary = screen.getByText("Scores").closest("summary");
    expect(summary).toHaveAttribute(
      "title",
      "Sentiment 0.65 · Topicality 1.20 · Base 0.80 · Rank 0.42",
    );
  });

  it("shows all four scores, each with its own bar, when expanded", () => {
    render(<ScoreDetails scores={scores} relative={relative} navigate={noop} />);

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
    render(<ScoreDetails scores={scores} relative={relative} navigate={noop} />);

    expect(screen.getAllByText("vs. this batch")).toHaveLength(3);
  });

  it("links to the algorithm page for the full explanation", () => {
    render(<ScoreDetails scores={scores} relative={relative} navigate={noop} />);

    const link = screen.getByRole("link", { name: /how these are calculated/i });
    expect(link).toHaveAttribute("href", "/algorithm");
  });

  it("intercepts a plain click for SPA navigation instead of a full page reload", () => {
    const navigate = vi.fn();
    render(<ScoreDetails scores={scores} relative={relative} navigate={navigate} />);

    fireEvent.click(screen.getByRole("link", { name: /how these are calculated/i }));

    expect(navigate).toHaveBeenCalledWith("/algorithm");
  });

  it("does not intercept a modified click (e.g. cmd-click to open in a new tab)", () => {
    const navigate = vi.fn();
    render(<ScoreDetails scores={scores} relative={relative} navigate={navigate} />);

    fireEvent.click(screen.getByRole("link", { name: /how these are calculated/i }), { metaKey: true });

    expect(navigate).not.toHaveBeenCalled();
  });
});
