import { expect, test } from "@playwright/test";

// Issue #60: collapsing an expanded post used to leave the scroll position
// stranded - the post shrinks, pulling everything below it upward, and the
// viewport ends up looking at later, unrelated posts with the collapsed
// post's own "Show less" toggle scrolled out of view above. Real
// scroll/layout behavior Vitest/JSDOM can't exercise.

test("collapsing a post that scrolled out of view brings it back into view", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Daily Life" }).click();

  // Matches the same button in both states, since its accessible name
  // flips between "Show more" and "Show less" - a locator captured by one
  // exact name would stop resolving once clicking changes it.
  const toggle = page.getByRole("button", { name: /^Show (more|less)$/ }).first();
  await toggle.waitFor();
  await toggle.click();
  await expect(toggle).toHaveText("Show less");

  // Pin the toggle to the very top of the viewport before collapsing - this
  // is what makes the test deterministic regardless of exactly how tall the
  // mock's long post renders at: with the toggle at the top edge, any
  // height the collapse removes from the paragraph above it is guaranteed
  // to push the toggle's new position above the viewport (top < 0) unless
  // the fix corrects it, matching the real bug (Playwright's own .click()
  // would otherwise scroll the target into view right before clicking
  // regardless of prior scroll position, masking the bug).
  await toggle.evaluate((el) => el.scrollIntoView({ block: "start" }));

  await toggle.click();
  await expect(toggle).toHaveText("Show more");

  await expect(toggle).toBeInViewport();
});
