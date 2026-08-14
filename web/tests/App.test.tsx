import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";

function mockFeedResponse() {
  return new Response(JSON.stringify({ posts: [], next_cursor: null }), { status: 200 });
}

describe("App header nav (issue #31: down to FAQ + GitHub icon, no collapse needed)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockFeedResponse()));
    window.history.pushState(null, "", "/");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows both nav links directly, with no toggle button", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: "FAQ" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "GitHub" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /menu/i })).not.toBeInTheDocument();
  });

  it("navigates to the FAQ page on click", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "FAQ" }));

    expect(screen.getByText(/what is goodgorithm/i)).toBeInTheDocument();
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
