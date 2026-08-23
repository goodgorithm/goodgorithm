import { expect, test } from "@playwright/test";

// IntersectionObserver-driven infinite scroll (Feed.tsx's sentinel div) -
// real cross-engine-sensitive surface area (IntersectionObserver has had
// real behavioral differences across engines historically), and something
// Vitest/JSDOM can't meaningfully exercise (no real viewport/scroll/
// intersection geometry).

test("scrolling to the bottom fetches and appends a second page", async ({ page }) => {
  await page.goto("/");
  // Arts & Culture is the one category with none of mock-api.mjs's other
  // special posts (isLong/hasLink) in it, so every post in it matches the
  // plain "Short uplifting post number N" pattern - avoids an off-by-one
  // from a differently-worded post in the mix. It's also the default tab,
  // but click explicitly rather than depending on that staying true.
  await page.getByRole("button", { name: "Arts & Culture" }).click();

  const posts = page.getByText(/^Short uplifting post number \d+/);
  await expect(posts).toHaveCount(20);

  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await expect(posts).toHaveCount(21, { timeout: 10_000 });
});
