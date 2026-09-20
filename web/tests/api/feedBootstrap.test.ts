import { afterEach, describe, expect, it } from "vitest";

import { consumeFeedBootstrap } from "../../src/api/feedBootstrap";
import type { FeedResponse } from "../../src/api/types";

const RESP: FeedResponse = { posts: [], next_cursor: null };

afterEach(() => {
  delete window.__feedBootstrap;
});

describe("consumeFeedBootstrap", () => {
  it("hands back the pre-started promise once, when there's no resume cursor", async () => {
    const promise = Promise.resolve(RESP);
    window.__feedBootstrap = { promise };

    const adopted = consumeFeedBootstrap(null);
    expect(adopted).toBe(promise);
    await expect(adopted).resolves.toBe(RESP);

    // one-shot: gone after the first consume
    expect(consumeFeedBootstrap(null)).toBeNull();
    expect(window.__feedBootstrap).toBeUndefined();
  });

  it("returns null when the inline script set nothing", () => {
    expect(consumeFeedBootstrap(null)).toBeNull();
  });

  it("does not adopt when page 1 carries a resume cursor", () => {
    window.__feedBootstrap = { promise: Promise.resolve(RESP) };
    expect(consumeFeedBootstrap("cursor-123")).toBeNull();
    // still there for the call it actually matches
    expect(consumeFeedBootstrap(null)).not.toBeNull();
  });
});
