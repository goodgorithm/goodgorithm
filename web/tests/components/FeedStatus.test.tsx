import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FeedEmpty, FeedError } from "../../src/components/FeedStatus";

describe("FeedError", () => {
  it("leads with plain user copy, not the raw request/status string", () => {
    render(<FeedError message="/v1/feed?limit=20 responded with 500" onRetry={() => {}} />);
    expect(screen.getByText(/something went wrong loading the feed/i)).toBeInTheDocument();
  });

  it("calls onRetry when the retry button is clicked", () => {
    const onRetry = vi.fn();
    render(<FeedError message="boom" onRetry={onRetry} />);

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    expect(onRetry).toHaveBeenCalled();
  });
});

describe("FeedEmpty", () => {
  it("shows a message naming the empty category", () => {
    render(<FeedEmpty category="diaries_daily_life" />);
    expect(screen.getByText(/no posts in daily life yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
