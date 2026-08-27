import { afterEach, describe, expect, it } from "vitest";

import { consumeFeedBootstrap } from "../../src/api/feedBootstrap";
import type { FeedResponse } from "../../src/api/types";

const RESP: FeedResponse = { posts: [], next_cursor: null };

afterEach(() => {
  delete window.__feedBootstrap;
});

describe("consumeFeedBootstrap", () => {
  it("hands back the pre-started promise once, for the default category with no cursor", async () => {
    const promise = Promise.resolve(RESP);
    window.__feedBootstrap = { promise };

    const adopted = consumeFeedBootstrap("arts_culture", null);
    expect(adopted).toBe(promise);
    await expect(adopted).resolves.toBe(RESP);

    // one-shot: gone after the first consume
    expect(consumeFeedBootstrap("arts_culture", null)).toBeNull();
    expect(window.__feedBootstrap).toBeUndefined();
  });

  it("returns null when the inline script set nothing", () => {
    expect(consumeFeedBootstrap("arts_culture", null)).toBeNull();
  });

  it("does not adopt for a non-default category (or the hidden full feed)", () => {
    window.__feedBootstrap = { promise: Promise.resolve(RESP) };

    expect(consumeFeedBootstrap("science_technology", null)).toBeNull();
    expect(consumeFeedBootstrap(null, null)).toBeNull();
    // still there for the call it actually matches
    expect(consumeFeedBootstrap("arts_culture", null)).not.toBeNull();
  });

  it("does not adopt when page 1 carries a resume cursor", () => {
    window.__feedBootstrap = { promise: Promise.resolve(RESP) };
    expect(consumeFeedBootstrap("arts_culture", "cursor-123")).toBeNull();
  });
});
