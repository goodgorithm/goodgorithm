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

describe("App on native platforms (issue #9)", () => {
  const useRegisterSW = vi.fn(() => ({}));

  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockFeedResponse()));
    window.history.pushState(null, "", "/");
    useRegisterSW.mockClear();
    // useRegisterSW is the literal call that registers a service worker
    // (vite-plugin-pwa's React hook, used inside UpdatePrompt) -- mocking
    // it directly and checking whether it was called at all is a more
    // faithful test of issue #9's actual concern than checking rendered
    // output, since UpdatePrompt's own visible text only ever appears
    // after a real onNeedReload event, which nothing here triggers either way.
    vi.doMock("virtual:pwa-register/react", () => ({ useRegisterSW }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
    vi.doUnmock("virtual:pwa-register/react");
    vi.doUnmock("@capacitor/core");
  });

  it("registers a service worker on web (sanity check for the native case below)", async () => {
    vi.doMock("@capacitor/core", () => ({ Capacitor: { isNativePlatform: () => false } }));
    const { default: WebApp } = await import("../src/App");

    render(<WebApp />);

    expect(useRegisterSW).toHaveBeenCalled();
  });

  it("never calls useRegisterSW when Capacitor.isNativePlatform() is true, so no service worker gets registered", async () => {
    vi.doMock("@capacitor/core", () => ({ Capacitor: { isNativePlatform: () => true } }));
    const { default: NativeApp } = await import("../src/App");

    render(<NativeApp />);

    expect(useRegisterSW).not.toHaveBeenCalled();
  });
});
