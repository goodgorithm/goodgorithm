import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ScrollToTopButton } from "../../src/components/ScrollToTopButton";

function setScrollY(value: number) {
  Object.defineProperty(window, "scrollY", { value, writable: true, configurable: true });
  fireEvent.scroll(window);
}

afterEach(() => {
  setScrollY(0);
});

describe("ScrollToTopButton", () => {
  it("is hidden while near the top of the page", () => {
    render(<ScrollToTopButton />);
    expect(screen.queryByRole("button", { name: "Scroll to top" })).not.toBeInTheDocument();
  });

  it("appears once scrolled past the threshold", () => {
    render(<ScrollToTopButton />);
    setScrollY(800);
    expect(screen.getByRole("button", { name: "Scroll to top" })).toBeInTheDocument();
  });

  it("scrolls the window to the top on click - a pure viewport scroll, not Feed's cursor-resetting Back to top", () => {
    render(<ScrollToTopButton />);
    setScrollY(800);

    const scrollTo = vi.fn();
    vi.stubGlobal("scrollTo", scrollTo);

    fireEvent.click(screen.getByRole("button", { name: "Scroll to top" }));

    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" });
    vi.unstubAllGlobals();
  });
});
