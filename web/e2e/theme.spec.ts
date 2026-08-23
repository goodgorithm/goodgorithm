import { expect, test } from "@playwright/test";

// Theming is driven entirely by the OS-level prefers-color-scheme media
// query (no manual toggle, see CLAUDE.md's Visual identity section) - real
// cross-engine-sensitive surface area, since media-query evaluation and
// custom-property resolution are each engine's own implementation, not
// something Vitest/JSDOM exercises at all.

test("theme.css's custom properties follow prefers-color-scheme", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  const lightBg = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--color-bg").trim(),
  );
  expect(lightBg).toBe("#ffffff");

  await page.emulateMedia({ colorScheme: "dark" });
  const darkBg = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--color-bg").trim(),
  );
  expect(darkBg).toBe("#121815");
});
