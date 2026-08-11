import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useFeed } from "../../src/api/useFeed";
import { loadCursor, saveCursor } from "../../src/lib/feedCursor";

function createWrapper() {
  const queryClient = new QueryClient();
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function mockFeedResponse(nextCursor: string | null) {
  return new Response(JSON.stringify({ posts: [], next_cursor: nextCursor }), { status: 200 });
}

describe("useFeed", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("starts from the top when no cursor is persisted", async () => {
    vi.mocked(fetch).mockResolvedValue(mockFeedResponse("next-1"));

    renderHook(() => useFeed(), { wrapper: createWrapper() });

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(calledUrl).not.toContain("cursor=");
  });

  it("resumes from a persisted cursor", async () => {
    saveCursor("resume-me");
    vi.mocked(fetch).mockResolvedValue(mockFeedResponse(null));

    renderHook(() => useFeed(), { wrapper: createWrapper() });

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(calledUrl).toContain("cursor=resume-me");
  });

  it("persists the next cursor once a page loads", async () => {
    vi.mocked(fetch).mockResolvedValue(mockFeedResponse("next-1"));

    const { result } = renderHook(() => useFeed(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(loadCursor()).toBe("next-1");
  });

  it("resetToTop clears the persisted cursor and re-fetches from the top", async () => {
    saveCursor("resume-me");
    vi.mocked(fetch).mockResolvedValue(mockFeedResponse(null));

    const { result } = renderHook(() => useFeed(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.resumed).toBe(true);

    act(() => result.current.resetToTop());

    await waitFor(() => expect(result.current.resumed).toBe(false));
    expect(loadCursor()).toBeNull();

    const lastCallUrl = vi.mocked(fetch).mock.calls.at(-1)?.[0] as string;
    expect(lastCallUrl).not.toContain("cursor=");
  });
});
