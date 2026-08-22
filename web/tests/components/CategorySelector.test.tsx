import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CategorySelector } from "../../src/components/CategorySelector";

describe("CategorySelector", () => {
  it("renders a chip for every category", () => {
    render(<CategorySelector selected="arts_culture" onSelect={() => {}} />);

    expect(screen.getByRole("button", { name: "Science & Technology" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Daily Life" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Food & Dining" })).toBeInTheDocument();
  });

  it("calls onSelect with the category key when a chip is clicked", () => {
    const onSelect = vi.fn();
    render(<CategorySelector selected="arts_culture" onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: "Daily Life" }));
    expect(onSelect).toHaveBeenCalledWith("diaries_daily_life");
  });

  it("renders categories alphabetically by label (issue #24)", () => {
    render(<CategorySelector selected="arts_culture" onSelect={() => {}} />);

    const labels = screen.getAllByRole("button").map((button) => button.textContent);
    expect(labels).toEqual(["Arts & Culture", "Daily Life", "Food & Dining", "Science & Technology"]);
  });
});
