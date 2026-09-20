import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useFeed } from "../../src/api/useFeed";
import { loadCursor, loadSeenIds, saveCursor } from "../../src/lib/feedCursor";

function createWrapper() {
  const queryClient = new QueryClient();
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function mockFeedResponse(nextCursor: string | null) {
  return new Response(JSON.stringify({ posts: [], next_cursor: nextCursor }), { status: 200 });
}

function mockFeedResponseWithPosts(ids: string[], nextCursor: string | null) {
  const posts = ids.map((id) => ({ id }));
  return new Response(JSON.stringify({ posts, next_cursor: nextCursor }), { status: 200 });
}

describe("useFeed", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    delete window.__feedBootstrap;
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

  it("adopts the inline-script feed promise for page 1 when there's no resume cursor", async () => {
    // The inline <script> in index.html pre-fetches the unfiltered feed and
    // parks the promise on window.__feedBootstrap; useFeed's first page
    // should use it instead of firing its own request.
    window.__feedBootstrap = {
      promise: Promise.resolve({ posts: [], next_cursor: "boot-next" }),
    };
    vi.mocked(fetch).mockResolvedValue(mockFeedResponse("net-next"));

    const { result } = renderHook(() => useFeed(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(fetch).not.toHaveBeenCalled();
    expect(loadCursor()).toBe("boot-next");
  });

  it("falls back to a normal fetch when a resume cursor is persisted", async () => {
    window.__feedBootstrap = {
      promise: Promise.resolve({ posts: [], next_cursor: "boot-next" }),
    };
    saveCursor("resume-me");
    vi.mocked(fetch).mockResolvedValue(mockFeedResponse(null));

    renderHook(() => useFeed(), { wrapper: createWrapper() });

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(vi.mocked(fetch).mock.calls[0][0] as string).toContain("cursor=resume-me");
  });

  it("persists the seen post ids once a page loads (issue #38)", async () => {
    vi.mocked(fetch).mockResolvedValue(mockFeedResponseWithPosts(["a", "b", "c"], "next-1"));

    const { result } = renderHook(() => useFeed(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(loadSeenIds()).toEqual(["a", "b", "c"]);
  });

  it("carries prior seen ids into a resumed session and merges them with the new pages", async () => {
    saveCursor("resume-me", ["x", "y"]);
    vi.mocked(fetch).mockResolvedValue(mockFeedResponseWithPosts(["a"], "next-1"));

    const { result } = renderHook(() => useFeed(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.data).toBeDefined());

    expect(result.current.carriedSeenIds).toEqual(["x", "y"]);
    expect(loadSeenIds()).toEqual(["x", "y", "a"]);
  });

  it("resetToTop drops the carried seen ids so the fresh session starts clean", async () => {
    saveCursor("resume-me", ["x", "y"]);
    vi.mocked(fetch).mockResolvedValue(mockFeedResponseWithPosts(["a"], "next-1"));

    const { result } = renderHook(() => useFeed(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.carriedSeenIds).toEqual(["x", "y"]));

    act(() => result.current.resetToTop());

    await waitFor(() => expect(result.current.carriedSeenIds).toEqual([]));
    expect(result.current.resumed).toBe(false);
  });
});
