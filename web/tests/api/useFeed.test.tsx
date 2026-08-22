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

    renderHook(() => useFeed("arts_culture"), { wrapper: createWrapper() });

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(calledUrl).not.toContain("cursor=");
  });

  it("resumes from a persisted cursor", async () => {
    saveCursor("arts_culture", "resume-me");
    vi.mocked(fetch).mockResolvedValue(mockFeedResponse(null));

    renderHook(() => useFeed("arts_culture"), { wrapper: createWrapper() });

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(calledUrl).toContain("cursor=resume-me");
  });

  it("persists the next cursor once a page loads", async () => {
    vi.mocked(fetch).mockResolvedValue(mockFeedResponse("next-1"));

    const { result } = renderHook(() => useFeed("arts_culture"), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(loadCursor("arts_culture")).toBe("next-1");
  });

  it("resetToTop clears the persisted cursor and re-fetches from the top", async () => {
    saveCursor("arts_culture", "resume-me");
    vi.mocked(fetch).mockResolvedValue(mockFeedResponse(null));

    const { result } = renderHook(() => useFeed("arts_culture"), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.resumed).toBe(true);

    act(() => result.current.resetToTop());

    await waitFor(() => expect(result.current.resumed).toBe(false));
    expect(loadCursor("arts_culture")).toBeNull();

    const lastCallUrl = vi.mocked(fetch).mock.calls.at(-1)?.[0] as string;
    expect(lastCallUrl).not.toContain("cursor=");
  });

  it("passes the selected category through to the /feed request", async () => {
    vi.mocked(fetch).mockResolvedValue(mockFeedResponse(null));

    renderHook(() => useFeed("science_technology"), { wrapper: createWrapper() });

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(calledUrl).toContain("category=science_technology");
  });

  it("resumes each category from its own persisted cursor, not another category's", async () => {
    // regression test: initialCursor used to be computed once at mount and
    // frozen, so switching category would silently resume using whatever
    // cursor was loaded for the category the hook happened to start on.
    saveCursor("science_technology", "tech-cursor");
    saveCursor("diaries_daily_life", "diaries_daily_life-cursor");
    vi.mocked(fetch).mockResolvedValue(mockFeedResponse(null));

    const { rerender } = renderHook(({ category }) => useFeed(category), {
      wrapper: createWrapper(),
      initialProps: { category: "science_technology" as const },
    });

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect((vi.mocked(fetch).mock.calls[0][0] as string)).toContain("cursor=tech-cursor");

    rerender({ category: "diaries_daily_life" as const });

    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some((call) => (call[0] as string).includes("cursor=diaries_daily_life-cursor"))).toBe(
        true,
      ),
    );
  });

  it("resetToTop on one category doesn't force another category back to the top", async () => {
    // regression test: resetToTop used to bump a single shared nonce, so
    // resetting one category's feed would also suppress resume for the
    // next category switched to, even if that category was never reset.
    saveCursor("science_technology", "tech-cursor");
    saveCursor("diaries_daily_life", "diaries_daily_life-cursor");
    vi.mocked(fetch).mockResolvedValue(mockFeedResponse(null));

    const { result, rerender } = renderHook(({ category }) => useFeed(category), {
      wrapper: createWrapper(),
      initialProps: { category: "science_technology" as const },
    });
    await waitFor(() => expect(result.current.resumed).toBe(true));

    act(() => result.current.resetToTop());
    await waitFor(() => expect(result.current.resumed).toBe(false));

    rerender({ category: "diaries_daily_life" as const });
    await waitFor(() => expect(result.current.resumed).toBe(true));
  });
});
