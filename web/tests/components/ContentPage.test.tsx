import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ContentPage } from "../../src/components/ContentPage";

describe("ContentPage", () => {
  it("renders the given markdown source", () => {
    render(<ContentPage source={"# Title\n\nBody text."} onBack={() => {}} />);

    expect(screen.getByRole("heading", { level: 1, name: "Title" })).toBeInTheDocument();
    expect(screen.getByText("Body text.")).toBeInTheDocument();
  });

  it("calls onBack when the back button is clicked", () => {
    const onBack = vi.fn();
    render(<ContentPage source="# Title" onBack={onBack} />);

    fireEvent.click(screen.getByRole("button", { name: /back to feed/i }));

    expect(onBack).toHaveBeenCalled();
  });
});
