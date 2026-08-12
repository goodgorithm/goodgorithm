import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchFeed, fetchHealth } from "../../src/api/client";

describe("api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches /health", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );

    const result = await fetchHealth();

    expect(result).toEqual({ status: "ok" });
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/health"));
  });

  it("fetches from /v1/feed, passing the cursor through when present", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ posts: [], next_cursor: null }), { status: 200 }),
    );

    await fetchFeed("abc123", 10);

    const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(calledUrl).toContain("/v1/feed?");
    expect(calledUrl).toContain("cursor=abc123");
    expect(calledUrl).toContain("limit=10");
  });

  it("passes the category through to /v1/feed when present", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ posts: [], next_cursor: null }), { status: 200 }),
    );

    await fetchFeed(null, 10, "technology");

    const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(calledUrl).toContain("category=technology");
  });

  it("omits the category param when not provided", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ posts: [], next_cursor: null }), { status: 200 }),
    );

    await fetchFeed(null, 10);

    const calledUrl = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(calledUrl).not.toContain("category=");
  });

  it("throws on a non-OK response", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response("nope", { status: 500 }));

    await expect(fetchHealth()).rejects.toThrow("500");
  });
});
