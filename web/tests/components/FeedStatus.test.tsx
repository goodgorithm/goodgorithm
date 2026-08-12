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
  it("shows a generic message for the unfiltered feed", () => {
    render(<FeedEmpty category={null} onShowFullFeed={() => {}} />);
    expect(screen.getByText("No posts yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("offers a way back to the full feed when a category is empty", () => {
    const onShowFullFeed = vi.fn();
    render(<FeedEmpty category="animals" onShowFullFeed={onShowFullFeed} />);

    expect(screen.getByText(/no posts in animals yet/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /show full feed/i }));

    expect(onShowFullFeed).toHaveBeenCalled();
  });
});
