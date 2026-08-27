import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FeedSkeleton } from "../../src/components/FeedSkeleton";

describe("FeedSkeleton", () => {
  it("renders an aria-hidden placeholder with three cards", () => {
    const { container } = render(<FeedSkeleton />);

    const wrapper = container.firstElementChild;
    expect(wrapper).toHaveAttribute("aria-hidden", "true");
    expect(wrapper?.children).toHaveLength(3);
  });

  it("does not look like real feed content", () => {
    render(<FeedSkeleton />);

    // getByRole("article") is how the feed's real posts are found in tests
    // and e2e -- the skeleton must never match it, or dedupe/count
    // assertions elsewhere would pick it up.
    expect(screen.queryAllByRole("article")).toHaveLength(0);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
  });
});
