import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { linkify } from "../../src/lib/linkify";

const bskyPermalink = "https://bsky.app/profile/did:plc:abc123/post/xyz";
const mastodonPermalink = "https://fosstodon.org/@someone/123";

describe("linkify", () => {
  it("leaves plain text untouched", () => {
    const { container } = render(<>{linkify("just a nice plain sentence", "bluesky", bskyPermalink)}</>);
    expect(container.textContent).toBe("just a nice plain sentence");
    expect(container.querySelector("a")).toBeNull();
  });

  it("strips trailing sentence punctuation from a linked URL", () => {
    const { getByRole } = render(
      <>{linkify("see https://example.com/a.", "bluesky", bskyPermalink)}</>,
    );
    const link = getByRole("link");
    expect(link).toHaveAttribute("href", "https://example.com/a");
    expect(link.textContent).toBe("https://example.com/a");
  });

  it("links a Bluesky hashtag to bsky.app search", () => {
    const { getByRole } = render(<>{linkify("#goodnews", "bluesky", bskyPermalink)}</>);
    expect(getByRole("link")).toHaveAttribute("href", "https://bsky.app/search?q=%23goodnews");
  });

  it("links a Mastodon hashtag to that instance's tag page", () => {
    const { getByRole } = render(<>{linkify("#goodnews", "mastodon", mastodonPermalink)}</>);
    expect(getByRole("link")).toHaveAttribute("href", "https://fosstodon.org/tags/goodnews");
  });

  it("links a URL and a hashtag together in one pass", () => {
    const { getAllByRole } = render(
      <>{linkify("check https://example.com out #nice", "bluesky", bskyPermalink)}</>,
    );
    const links = getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute("href", "https://example.com");
    expect(links[1]).toHaveAttribute("href", "https://bsky.app/search?q=%23nice");
  });
});
