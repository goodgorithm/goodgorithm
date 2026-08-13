import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";

function mockFeedResponse() {
  return new Response(JSON.stringify({ posts: [], next_cursor: null }), { status: 200 });
}

describe("App header nav toggle (issue #27)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockFeedResponse()));
    window.history.pushState(null, "", "/");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("starts collapsed", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: "Open menu" })).toHaveAttribute("aria-expanded", "false");
  });

  it("expands and collapses on toggle click", () => {
    render(<App />);
    const toggle = screen.getByRole("button", { name: "Open menu" });

    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Close menu" })).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(screen.getByRole("button", { name: "Close menu" }));
    expect(screen.getByRole("button", { name: "Open menu" })).toHaveAttribute("aria-expanded", "false");
  });

  it("nav links are always present in the DOM regardless of toggle state -- CSS handles the narrow-viewport collapse, not conditional rendering", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: "Our mission" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "GitHub" })).toBeInTheDocument();
  });

  it("closes the menu after navigating, so it doesn't stay open behind the new page", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    fireEvent.click(screen.getByRole("button", { name: "Our mission" }));

    expect(screen.getByRole("button", { name: "Open menu" })).toHaveAttribute("aria-expanded", "false");
  });
});
