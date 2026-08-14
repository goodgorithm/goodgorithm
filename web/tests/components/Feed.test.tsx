import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { FeedPost } from "../../src/api/types";
import { Feed } from "../../src/components/Feed";
import * as useFeedModule from "../../src/api/useFeed";

vi.mock("../../src/api/useFeed");

function makePost(id: string, text: string): FeedPost {
  return {
    id,
    source: "bluesky",
    author_id: `author-${id}`,
    text,
    created_at: new Date().toISOString(),
    entities: [],
    permalink: `https://example.com/post/${id}`,
    author: { display_name: null, avatar_url: null },
    scores: { sentiment: 0.5, topicality: 0.5, base: 0.5, rank: 0.5 },
    pipeline_version: "v1",
    attachments: [],
    sensitive: false,
    category: null,
  };
}

function mockUseFeed(pages: FeedPost[][]) {
  vi.mocked(useFeedModule.useFeed).mockReturnValue({
    data: { pages: pages.map((posts) => ({ posts, next_cursor: null })), pageParams: [] },
    error: null,
    isPending: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    hasNextPage: false,
    resumed: false,
    resetToTop: vi.fn(),
    refetch: vi.fn(),
    // biome-ignore/eslint-ignore: partial mock of react-query's return shape, only what Feed.tsx actually reads
  } as unknown as ReturnType<typeof useFeedModule.useFeed>);
}

describe("Feed", () => {
  it("renders each post once when pages don't overlap", () => {
    mockUseFeed([[makePost("1", "First post"), makePost("2", "Second post")]]);
    render(<Feed />);

    expect(screen.getByText("First post")).toBeInTheDocument();
    expect(screen.getByText("Second post")).toBeInTheDocument();
  });

  it("dedupes a post id that appears on more than one page (issue #36)", () => {
    // The exact shape of the bug: api/'s rank_score-keyset pagination can
    // occasionally re-serve an already-shown post on a later page, since
    // rank_score is mutated in place by a concurrent background re-ranking
    // job rather than being a stable, append-only value. This doesn't fix
    // the server doing that, just stops it from rendering twice.
    const repeated = makePost("1", "Repeated post");
    mockUseFeed([[repeated, makePost("2", "Second post")], [repeated, makePost("3", "Third post")]]);

    render(<Feed />);

    expect(screen.getAllByText("Repeated post")).toHaveLength(1);
    expect(screen.getByText("Second post")).toBeInTheDocument();
    expect(screen.getByText("Third post")).toBeInTheDocument();
  });

  it("keeps the earlier-page occurrence's position when deduping", () => {
    // Renders in document order, so the kept copy should still appear
    // before posts that were only ever on the second page.
    const repeated = makePost("1", "Repeated post");
    mockUseFeed([[repeated, makePost("2", "Second post")], [makePost("3", "Third post"), repeated]]);

    render(<Feed />);

    const texts = screen.getAllByRole("article").map((el) => el.textContent);
    const repeatedIndex = texts.findIndex((t) => t?.includes("Repeated post"));
    const thirdIndex = texts.findIndex((t) => t?.includes("Third post"));
    expect(repeatedIndex).toBeLessThan(thirdIndex);
  });
});
