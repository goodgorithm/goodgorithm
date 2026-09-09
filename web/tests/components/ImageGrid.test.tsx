import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Attachment } from "../../src/api/types";
import { ImageGrid } from "../../src/components/ImageGrid";

type ImageAttachment = Extract<Attachment, { kind: "image" }>;

function img(n: number, extra: Partial<ImageAttachment> = {}): ImageAttachment {
  return {
    kind: "image",
    thumbnailUrl: `https://cdn.bsky.app/img/feed_thumbnail/plain/did/cid${n}@jpeg`,
    fullUrl: `https://cdn.bsky.app/img/feed_fullsize/plain/did/cid${n}@jpeg`,
    alt: `photo ${n}`,
    width: 800,
    height: 600,
    ...extra,
  };
}

describe("ImageGrid", () => {
  it("renders nothing for an empty list", () => {
    const { container } = render(<ImageGrid images={[]} sensitive={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders each image as a thumbnail linking to its fullsize URL", () => {
    const images = [img(1), img(2), img(3)];
    render(<ImageGrid images={images} sensitive={false} />);

    for (const image of images) {
      const el = screen.getByAltText(image.alt as string);
      expect(el).toHaveAttribute("src", image.thumbnailUrl);
      expect(el).toHaveStyle({ aspectRatio: "800 / 600" });
      expect(el.closest("a")).toHaveAttribute("href", image.fullUrl);
    }
  });

  it("caps the grid at 4 images", () => {
    render(<ImageGrid images={[img(1), img(2), img(3), img(4), img(5)]} sensitive={false} />);
    expect(screen.getAllByRole("img")).toHaveLength(4);
  });

  it("falls back to a 16/9 box when the source gave no dimensions", () => {
    render(<ImageGrid images={[img(1, { width: null, height: null })]} sensitive={false} />);
    expect(screen.getByAltText("photo 1")).toHaveStyle({ aspectRatio: "16 / 9" });
  });

  it("lazy-loads every image and sets no fetchpriority by default", () => {
    render(<ImageGrid images={[img(1), img(2)]} sensitive={false} />);
    for (const el of screen.getAllByRole("img")) {
      expect(el).toHaveAttribute("loading", "lazy");
      expect(el).not.toHaveAttribute("fetchpriority");
    }
  });

  it("eager-loads only the first image at high priority when priority is set", () => {
    render(<ImageGrid images={[img(1), img(2)]} sensitive={false} priority />);
    const [first, second] = screen.getAllByRole("img");
    expect(first).toHaveAttribute("loading", "eager");
    expect(first).toHaveAttribute("fetchpriority", "high");
    expect(second).toHaveAttribute("loading", "lazy");
    expect(second).not.toHaveAttribute("fetchpriority");
  });

  describe("failed-load escalation", () => {
    afterEach(() => vi.useRealTimers());

    it("retries the thumbnail with a cache-bust param ~1s after the first error", async () => {
      vi.useFakeTimers();
      render(<ImageGrid images={[img(1)]} sensitive={false} />);
      const el = screen.getByAltText("photo 1");

      fireEvent.error(el);
      // the retry is deferred -- src is unchanged until the timer fires
      expect(el).toHaveAttribute("src", img(1).thumbnailUrl);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(el).toHaveAttribute("src", "https://cdn.bsky.app/img/feed_thumbnail/plain/did/cid1@jpeg?r=1");
    });

    it("swaps to the fullsize URL when the retry also fails, then shows a placeholder", async () => {
      vi.useFakeTimers();
      render(<ImageGrid images={[img(1)]} sensitive={false} />);
      const el = screen.getByAltText("photo 1");

      fireEvent.error(el);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      // retry failed -> fullsize, immediately (no further wait)
      fireEvent.error(el);
      expect(el).toHaveAttribute("src", img(1).fullUrl);

      // fullsize failed -> placeholder replaces the <img>, box still reserved,
      // still inside the fullsize link
      fireEvent.error(el);
      expect(screen.queryByRole("img")).not.toBeInTheDocument();
      const placeholder = screen.getByText(/tap to open/i);
      expect(placeholder).toHaveStyle({ aspectRatio: "800 / 600" });
      expect(placeholder.closest("a")).toHaveAttribute("href", img(1).fullUrl);
    });

    it("stays put once a retry actually loads", async () => {
      vi.useFakeTimers();
      render(<ImageGrid images={[img(1)]} sensitive={false} />);
      const el = screen.getByAltText("photo 1");

      fireEvent.error(el);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      fireEvent.load(el);

      expect(el).toHaveAttribute("src", "https://cdn.bsky.app/img/feed_thumbnail/plain/did/cid1@jpeg?r=1");
      expect(screen.getByRole("img")).toBeInTheDocument();
    });

    it("does not update state if the cell unmounts during the retry wait", async () => {
      vi.useFakeTimers();
      const { unmount } = render(<ImageGrid images={[img(1)]} sensitive={false} />);
      fireEvent.error(screen.getByAltText("photo 1"));
      unmount();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      // no throw / no "state update on unmounted component" -- the pending
      // timer was cleared on unmount
    });
  });
});
