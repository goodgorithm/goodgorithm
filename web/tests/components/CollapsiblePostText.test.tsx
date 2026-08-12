import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CollapsiblePostText } from "../../src/components/CollapsiblePostText";

const shortText = "A genuinely nice thing happened today.";
const longText = "This is a very long post. ".repeat(20); // well over the threshold
const permalink = "https://bsky.app/profile/did:plc:abc123/post/xyz";

describe("CollapsiblePostText", () => {
  it("renders short posts with no toggle", () => {
    render(<CollapsiblePostText text={shortText} source="bluesky" permalink={permalink} />);

    expect(screen.getByText(shortText)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("collapses long posts behind a Show more toggle", () => {
    render(<CollapsiblePostText text={longText} source="bluesky" permalink={permalink} />);

    expect(screen.getByRole("button", { name: "Show more" })).toBeInTheDocument();
  });

  it("expands and re-collapses on toggle", () => {
    render(<CollapsiblePostText text={longText} source="bluesky" permalink={permalink} />);

    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(screen.getByRole("button", { name: "Show less" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show less" }));
    expect(screen.getByRole("button", { name: "Show more" })).toBeInTheDocument();
  });

  it("renders a URL in the text as a real link", () => {
    render(
      <CollapsiblePostText
        text="check this out: https://example.com/article."
        source="bluesky"
        permalink={permalink}
      />,
    );

    const link = screen.getByRole("link", { name: "https://example.com/article" });
    expect(link).toHaveAttribute("href", "https://example.com/article");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("renders a hashtag as a link back to the source platform", () => {
    render(<CollapsiblePostText text="loving this #sunshine today" source="bluesky" permalink={permalink} />);

    const link = screen.getByRole("link", { name: "#sunshine" });
    expect(link).toHaveAttribute("href", "https://bsky.app/search?q=%23sunshine");
  });
});
