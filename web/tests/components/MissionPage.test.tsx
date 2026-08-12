import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MissionPage } from "../../src/components/MissionPage";

describe("MissionPage", () => {
  it("renders the mission content", () => {
    render(<MissionPage onBack={() => {}} />);

    expect(screen.getByRole("heading", { level: 1, name: "Our mission" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "How we decide" })).toBeInTheDocument();
  });

  it("calls onBack when the back button is clicked", () => {
    const onBack = vi.fn();
    render(<MissionPage onBack={onBack} />);

    fireEvent.click(screen.getByRole("button", { name: /back to feed/i }));

    expect(onBack).toHaveBeenCalled();
  });
});
