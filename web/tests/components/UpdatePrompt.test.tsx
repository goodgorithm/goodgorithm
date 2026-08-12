import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

let capturedOnNeedReload: (() => void) | undefined;

// virtual:pwa-register/react only exists via the VitePWA plugin's build-time
// module resolution - mocked here rather than relying on that resolving the
// same way under vitest, the standard pattern for testing this hook.
vi.mock("virtual:pwa-register/react", () => ({
  useRegisterSW: (options: { onNeedReload?: () => void }) => {
    capturedOnNeedReload = options.onNeedReload;
    return { needRefresh: [false, vi.fn()], offlineReady: [false, vi.fn()], updateServiceWorker: vi.fn() };
  },
}));

const { UpdatePrompt } = await import("../../src/components/UpdatePrompt");

describe("UpdatePrompt", () => {
  it("renders nothing before an update is available", () => {
    render(<UpdatePrompt />);
    expect(screen.queryByText(/new version/i)).not.toBeInTheDocument();
  });

  it("shows a reload banner once the service worker signals a reload is needed", () => {
    render(<UpdatePrompt />);

    act(() => capturedOnNeedReload?.());

    expect(screen.getByText(/new version is available/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reload/i })).toBeInTheDocument();
  });

  it("reloads the page when the reload button is clicked", () => {
    const reloadSpy = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload: reloadSpy });

    render(<UpdatePrompt />);
    act(() => capturedOnNeedReload?.());
    screen.getByRole("button", { name: /reload/i }).click();

    expect(reloadSpy).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("dismisses the banner without reloading when Dismiss is clicked", () => {
    render(<UpdatePrompt />);
    act(() => capturedOnNeedReload?.());

    act(() => screen.getByRole("button", { name: /dismiss/i }).click());

    expect(screen.queryByText(/new version is available/i)).not.toBeInTheDocument();
  });
});
