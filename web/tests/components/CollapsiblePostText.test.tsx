import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CollapsiblePostText } from "../../src/components/CollapsiblePostText";

const shortText = "A genuinely nice thing happened today.";
const longText = "This is a very long post. ".repeat(20); // well over the threshold
const permalink = "https://bsky.app/profile/did:plc:abc123/post/xyz";

// JSDOM doesn't implement scrollIntoView at all (throws unless stubbed) or
// real layout (getBoundingClientRect always returns zeros) - both are
// stubbed per test below to simulate "scrolled out of view" vs. "still
// visible" without a real browser.
beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

describe("CollapsiblePostText", () => {
  it("renders short posts with no toggle", () => {
    render(<CollapsiblePostText text={shortText} emojis={[]} source="bluesky" permalink={permalink} />);

    expect(screen.getByText(shortText)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("collapses long posts behind a Show more toggle", () => {
    render(<CollapsiblePostText text={longText} emojis={[]} source="bluesky" permalink={permalink} />);

    expect(screen.getByRole("button", { name: "Show more" })).toBeInTheDocument();
  });

  it("expands and re-collapses on toggle", () => {
    render(<CollapsiblePostText text={longText} emojis={[]} source="bluesky" permalink={permalink} />);

    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(screen.getByRole("button", { name: "Show less" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show less" }));
    expect(screen.getByRole("button", { name: "Show more" })).toBeInTheDocument();
  });

  it("scrolls the post back into view when collapsing pushes it above the viewport (issue #60)", () => {
    const { container } = render(<CollapsiblePostText text={longText} emojis={[]} source="bluesky" permalink={permalink} />);
    // Simulates the post's top having scrolled above the viewport as a
    // result of the collapse shrinking its height.
    container.querySelector("div")!.getBoundingClientRect = () => ({ top: -200 }) as DOMRect;

    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Show less" }));
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith({ block: "start" });
  });

  it("does not scroll on collapse when the post is still in view", () => {
    const { container } = render(<CollapsiblePostText text={longText} emojis={[]} source="bluesky" permalink={permalink} />);
    container.querySelector("div")!.getBoundingClientRect = () => ({ top: 100 }) as DOMRect;

    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    fireEvent.click(screen.getByRole("button", { name: "Show less" }));

    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("renders a URL in the text as a real link", () => {
    render(
      <CollapsiblePostText
        text="check this out: https://example.com/article."
        emojis={[]}
        source="bluesky"
        permalink={permalink}
      />,
    );

    const link = screen.getByRole("link", { name: "https://example.com/article" });
    expect(link).toHaveAttribute("href", "https://example.com/article");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("renders a hashtag as a link back to the source platform", () => {
    render(<CollapsiblePostText text="loving this #sunshine today" emojis={[]} source="bluesky" permalink={permalink} />);

    const link = screen.getByRole("link", { name: "#sunshine" });
    expect(link).toHaveAttribute("href", "https://bsky.app/search?q=%23sunshine");
  });

  it("renders a custom emoji shortcode alongside a link in the same post (issue #77)", () => {
    render(
      <CollapsiblePostText
        text="so happy :blobcat: check this out https://example.com/a"
        emojis={[{ shortcode: "blobcat", url: "https://example.com/blobcat.png" }]}
        source="bluesky"
        permalink={permalink}
      />,
    );

    expect(screen.queryByText(":blobcat:")).not.toBeInTheDocument();
    expect(screen.getByAltText(":blobcat:")).toHaveAttribute("src", "https://example.com/blobcat.png");
    expect(screen.getByRole("link", { name: "https://example.com/a" })).toBeInTheDocument();
  });
});
