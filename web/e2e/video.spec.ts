import { expect, test } from "@playwright/test";

// Regression coverage for issue #66: two bugs, found together, both
// invisible to Vitest/JSDOM (no real browser media APIs) and to the
// original mock data (a plain MP4 never exercises VideoPlayer's hls.js
// branch at all). Runs across chromium/firefox/webkit via
// playwright.config.ts's projects - the first bug was Chromium-specific
// (canPlayType() answering "maybe" for HLS), so single-browser coverage
// would have missed it entirely.

test("a real HLS video actually engages hls.js and loads, across engines", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Science & Technology" }).click();

  const revealButton = page.getByRole("button", { name: "Show video" });
  await revealButton.waitFor();
  await revealButton.click();

  const video = page.locator("video");
  await video.waitFor();

  // The core #66 assertion: a native <video src="...m3u8"> can't play HLS
  // and gets stuck at readyState 0 forever, completely silently (no error
  // event). hls.js attaching successfully replaces src with a blob:
  // MediaSource URL and readyState reaches HAVE_ENOUGH_DATA (4).
  await expect
    .poll(async () => video.evaluate((el: HTMLVideoElement) => el.currentSrc), { timeout: 10_000 })
    .toMatch(/^blob:/);
  await expect
    .poll(async () => video.evaluate((el: HTMLVideoElement) => el.readyState), { timeout: 10_000 })
    .toBe(4);

  const blobUrlAfterReveal = await video.evaluate((el: HTMLVideoElement) => el.currentSrc);

  // The second #66 bug: SensitiveMedia used to remount VideoPlayer on
  // every reveal/hide toggle, tearing down and losing the hls.js
  // attachment. Toggling hide then show again must keep the exact same
  // blob: URL (same MediaSource, same underlying video element) - a new
  // blob URL here would mean a remount happened.
  await page.getByRole("button", { name: "Hide video" }).click();
  await page.getByRole("button", { name: "Show video" }).click();

  const blobUrlAfterToggle = await video.evaluate((el: HTMLVideoElement) => el.currentSrc);
  expect(blobUrlAfterToggle).toBe(blobUrlAfterReveal);
});
