import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { FeedPost } from "../../src/api/types";
import { PostCard } from "../../src/components/PostCard";

const noRelative = { topicality: 0, base: 0, rank: 0 };
const noop = () => {};

const bskyPost: FeedPost = {
  id: "1",
  source: "bluesky",
  author_id: "did:plc:abc123",
  text: "A genuinely nice thing happened today.",
  created_at: new Date().toISOString(),
  entities: ["nice thing"],
  permalink: "https://bsky.app/profile/did:plc:abc123/post/xyz",
  author: { display_name: null, avatar_url: null },
  scores: { sentiment: 0.9, topicality: 1.2, base: 1.1, rank: 0.8 },
  pipeline_version: "v1",
  attachments: [],
  sensitive: false,
  category: null,
};

const mastodonPost: FeedPost = {
  ...bskyPost,
  id: "2",
  source: "mastodon",
  permalink: "https://fosstodon.org/@someone/123",
  author: { display_name: "Someone Nice", avatar_url: "https://example.com/a.png" },
};

describe("PostCard", () => {
  it("renders post text, source badge, and permalink", () => {
    render(<PostCard post={bskyPost} relative={noRelative} navigate={noop} />);

    expect(screen.getByText(bskyPost.text)).toBeInTheDocument();
    expect(screen.getByText("Bluesky")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view original/i })).toHaveAttribute(
      "href",
      bskyPost.permalink,
    );
  });

  it("omits author name/avatar for Bluesky (no identity data available)", () => {
    render(<PostCard post={bskyPost} relative={noRelative} navigate={noop} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("shows author name and avatar for Mastodon when available", () => {
    render(<PostCard post={mastodonPost} relative={noRelative} navigate={noop} />);
    expect(screen.getByText("Someone Nice")).toBeInTheDocument();
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("exposes raw scores behind a details toggle", () => {
    render(<PostCard post={bskyPost} relative={noRelative} navigate={noop} />);
    expect(screen.getByText("Scores")).toBeInTheDocument();
    expect(screen.getByText("0.90")).toBeInTheDocument();
  });

  it("links Report to the moderation issue template, pre-filled with the permalink (issue #7)", () => {
    render(<PostCard post={bskyPost} relative={noRelative} navigate={noop} />);

    const reportLink = screen.getByRole("link", { name: "Report" });
    const href = reportLink.getAttribute("href")!;
    expect(href).toMatch(
      /^https:\/\/github\.com\/goodgorithm\/goodgorithm\/issues\/new\?/,
    );

    const params = new URL(href).searchParams;
    expect(params.get("template")).toBe("moderation_report.md");
    expect(params.get("body")).toContain(bskyPost.permalink);
  });
});
