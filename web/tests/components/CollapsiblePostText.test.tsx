import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CollapsiblePostText } from "../../src/components/CollapsiblePostText";

const shortText = "A genuinely nice thing happened today.";
const longText = "This is a very long post. ".repeat(20); // well over the threshold

describe("CollapsiblePostText", () => {
  it("renders short posts with no toggle", () => {
    render(<CollapsiblePostText text={shortText} />);

    expect(screen.getByText(shortText)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("collapses long posts behind a Show more toggle", () => {
    render(<CollapsiblePostText text={longText} />);

    expect(screen.getByRole("button", { name: "Show more" })).toBeInTheDocument();
  });

  it("expands and re-collapses on toggle", () => {
    render(<CollapsiblePostText text={longText} />);

    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(screen.getByRole("button", { name: "Show less" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show less" }));
    expect(screen.getByRole("button", { name: "Show more" })).toBeInTheDocument();
  });
});
