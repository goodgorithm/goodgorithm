import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CategorySelector } from "../../src/components/CategorySelector";

describe("CategorySelector", () => {
  it("renders a chip for every category plus Full feed", () => {
    render(<CategorySelector selected={null} onSelect={() => {}} />);

    expect(screen.getByRole("button", { name: "Technology" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Animals" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Science & Discovery" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Full feed" })).toBeInTheDocument();
  });

  it("calls onSelect with the category key when a chip is clicked", () => {
    const onSelect = vi.fn();
    render(<CategorySelector selected={null} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: "Animals" }));
    expect(onSelect).toHaveBeenCalledWith("animals");
  });

  it("calls onSelect with null when Full feed is clicked", () => {
    const onSelect = vi.fn();
    render(<CategorySelector selected="technology" onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: "Full feed" }));
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("renders categories alphabetically by label, with Full feed last (issue #24)", () => {
    render(<CategorySelector selected={null} onSelect={() => {}} />);

    const labels = screen.getAllByRole("button").map((button) => button.textContent);
    expect(labels).toEqual([
      "Animals",
      "Arts & Culture",
      "Environment & Nature",
      "Health & Recovery",
      "Kindness & Community",
      "Science & Discovery",
      "Sports & Achievement",
      "Technology",
      "Full feed",
    ]);
  });
});
