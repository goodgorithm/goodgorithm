import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderEmojiShortcodes } from "../../src/lib/emoji";

describe("renderEmojiShortcodes", () => {
  it("leaves plain text untouched when there are no emojis", () => {
    const { container } = render(<>{renderEmojiShortcodes("just a nice plain sentence", [])}</>);
    expect(container.textContent).toBe("just a nice plain sentence");
    expect(container.querySelector("img")).toBeNull();
  });

  it("substitutes a known shortcode with its image", () => {
    const { container, getByAltText } = render(
      <>
        {renderEmojiShortcodes("Volodymyr Zelenskyy :bot:", [
          { shortcode: "bot", url: "https://example.com/bot.png" },
        ])}
      </>,
    );
    expect(container.textContent).toBe("Volodymyr Zelenskyy ");
    expect(getByAltText(":bot:")).toHaveAttribute("src", "https://example.com/bot.png");
  });

  it("leaves a :word:-shaped span alone when it isn't in the emojis array (issue #77)", () => {
    const { container } = render(
      <>{renderEmojiShortcodes("time :10:30: to go", [{ shortcode: "bot", url: "https://example.com/bot.png" }])}</>,
    );
    expect(container.textContent).toBe("time :10:30: to go");
    expect(container.querySelector("img")).toBeNull();
  });

  it("substitutes multiple distinct shortcodes in one pass", () => {
    const { getByAltText } = render(
      <>
        {renderEmojiShortcodes(":wave: hello :blobcat:", [
          { shortcode: "wave", url: "https://example.com/wave.png" },
          { shortcode: "blobcat", url: "https://example.com/blobcat.png" },
        ])}
      </>,
    );
    expect(getByAltText(":wave:")).toHaveAttribute("src", "https://example.com/wave.png");
    expect(getByAltText(":blobcat:")).toHaveAttribute("src", "https://example.com/blobcat.png");
  });
});
