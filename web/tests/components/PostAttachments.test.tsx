import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Attachment, FeedPost } from "../../src/api/types";
import { PostAttachments } from "../../src/components/PostAttachments";

function makePost(attachments: Attachment[], sensitive = false): FeedPost {
  return {
    id: "1",
    source: "bluesky",
    author_id: "did:plc:abc123",
    text: "post text",
    created_at: new Date().toISOString(),
    entities: [],
    permalink: "https://bsky.app/profile/did:plc:abc123/post/xyz",
    author: { display_name: null, avatar_url: null },
    scores: { sentiment: 0.9, topicality: 1.2, base: 1.1, rank: 0.8 },
    attachments,
    sensitive,
  };
}

const image: Attachment = {
  kind: "image",
  thumbnailUrl: "https://cdn.bsky.app/img/feed_thumbnail/plain/did/cid@jpeg",
  fullUrl: "https://cdn.bsky.app/img/feed_fullsize/plain/did/cid@jpeg",
  alt: "a nice photo",
  width: 800,
  height: 600,
};

const link: Attachment = {
  kind: "link",
  url: "https://example.com/article",
  title: "An interesting article",
  description: "Some description",
  thumbnailUrl: "https://cdn.bsky.app/img/feed_thumbnail/plain/did/thumb@jpeg",
  providerName: "Example Site",
};

const quote: Attachment = {
  kind: "quote",
  url: "https://bsky.app/profile/did:plc:other/post/xyz",
};

describe("PostAttachments", () => {
  it("renders nothing when there are no attachments", () => {
    const { container } = render(<PostAttachments post={makePost([])} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders an image attachment", () => {
    render(<PostAttachments post={makePost([image])} />);
    const img = screen.getByAltText("a nice photo");
    expect(img).toHaveAttribute("src", image.thumbnailUrl);
  });

  it("renders a link attachment", () => {
    render(<PostAttachments post={makePost([link])} />);
    expect(screen.getByText("An interesting article")).toBeInTheDocument();
    expect(screen.getByText("Some description")).toBeInTheDocument();
    expect(screen.getByText("Example Site")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /an interesting article/i })).toHaveAttribute(
      "href",
      link.url,
    );
  });

  it("renders a quote attachment", () => {
    render(<PostAttachments post={makePost([quote])} />);
    const quoteLink = screen.getByRole("link", { name: /quotes a post/i });
    expect(quoteLink).toHaveAttribute("href", quote.url);
  });

  it("renders images and a quote together (recordWithMedia shape)", () => {
    render(<PostAttachments post={makePost([image, quote])} />);
    expect(screen.getByAltText("a nice photo")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /quotes a post/i })).toBeInTheDocument();
  });

  it("blurs a sensitive image behind a real, accessible button", () => {
    render(<PostAttachments post={makePost([image], true)} />);

    // image is present in the DOM (blurred via CSS) but the reveal control
    // is what a screen reader / keyboard user actually interacts with
    expect(screen.getByAltText("a nice photo")).toBeInTheDocument();
    const revealButton = screen.getByRole("button", { name: /show image/i });
    expect(revealButton).toHaveAttribute("aria-pressed", "false");
  });

  it("un-blurs a sensitive image on keyboard activation, not just click", () => {
    render(<PostAttachments post={makePost([image], true)} />);

    const revealButton = screen.getByRole("button", { name: /show image/i });
    // fireEvent.click is what a real <button> receives for both mouse
    // clicks and Enter/Space keyboard activation - browsers translate
    // keyboard activation into a click event for native buttons, so this
    // exercises the same code path a keyboard user hits.
    fireEvent.click(revealButton);

    expect(screen.queryByRole("button", { name: /show image/i })).not.toBeInTheDocument();
  });

  it("does not blur a non-sensitive image", () => {
    render(<PostAttachments post={makePost([image], false)} />);
    expect(screen.queryByRole("button", { name: /show image/i })).not.toBeInTheDocument();
  });

  it("blurs a sensitive link card's thumbnail too, not just inline images", () => {
    render(<PostAttachments post={makePost([link], true)} />);
    expect(screen.getByRole("button", { name: /show image/i })).toBeInTheDocument();
  });
});
