import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HeaderNav } from "../../src/components/HeaderNav";

const PAGES = [
  { path: "/faq", label: "FAQ" },
  { path: "/updates", label: "Updates" },
  { path: "/privacy", label: "Privacy" },
];

function stubViewport(narrow: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: narrow,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HeaderNav — wide viewport (inline)", () => {
  it("renders every non-active page link plus GitHub, and no burger", () => {
    const onNavigate = vi.fn();
    render(<HeaderNav pages={PAGES} activePath="/" onNavigate={onNavigate} />);

    expect(screen.getByRole("button", { name: "FAQ" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Updates" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Privacy" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "GitHub" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Menu" })).not.toBeInTheDocument();
  });

  it("omits the link for the active page", () => {
    render(<HeaderNav pages={PAGES} activePath="/faq" onNavigate={vi.fn()} />);

    expect(screen.queryByRole("button", { name: "FAQ" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Updates" })).toBeInTheDocument();
  });

  it("calls onNavigate with the page path on click", () => {
    const onNavigate = vi.fn();
    render(<HeaderNav pages={PAGES} activePath="/" onNavigate={onNavigate} />);

    fireEvent.click(screen.getByRole("button", { name: "Updates" }));

    expect(onNavigate).toHaveBeenCalledWith("/updates");
  });
});

describe("HeaderNav — narrow viewport (burger)", () => {
  it("collapses the links behind a Menu button that toggles them", () => {
    stubViewport(true);
    render(<HeaderNav pages={PAGES} activePath="/" onNavigate={vi.fn()} />);

    const burger = screen.getByRole("button", { name: "Menu" });
    expect(burger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "FAQ" })).not.toBeInTheDocument();

    fireEvent.click(burger);

    expect(burger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "FAQ" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "GitHub" })).toBeInTheDocument();
  });

  it("navigates and closes the menu when a link is chosen", () => {
    stubViewport(true);
    const onNavigate = vi.fn();
    render(<HeaderNav pages={PAGES} activePath="/" onNavigate={onNavigate} />);

    fireEvent.click(screen.getByRole("button", { name: "Menu" }));
    fireEvent.click(screen.getByRole("button", { name: "Privacy" }));

    expect(onNavigate).toHaveBeenCalledWith("/privacy");
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "Privacy" })).not.toBeInTheDocument();
  });

  it("closes the menu on Escape", () => {
    stubViewport(true);
    render(<HeaderNav pages={PAGES} activePath="/" onNavigate={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Menu" }));
    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
  });
});
