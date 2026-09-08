// Regenerates web/public/og-image.png -- the 1200x630 link-preview card
// (og:image / twitter:image, referenced from index.html). Renders a
// self-contained HTML lockup (mark + wordmark + the header tagline) with
// Manrope inlined, screenshots it with the same Chromium the e2e suite
// uses. No network, no dev server.
//
//   cd web && npm run gen:og
//
// Re-run whenever the mark, the wordmark colours, or the tagline change.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { chromium } from "@playwright/test";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, "..");

const OUT = resolve(webRoot, "public/og-image.png");
const WIDTH = 1200;
const HEIGHT = 630;

// Dark warm-near-black, matching the theme's dark surface and the icon
// artboard. Colours are the theme's dark-mode tokens.
const BG = "#121815";
const ACCENT = "#3ecb79";
const TEXT = "#ecf3ef";
const MUTED = "#9fada6";

// The header tagline, kept in step with index.html's .gg-shell-tagline.
const TAGLINE = "Uplifting posts, honestly ranked.";

// The winking-g mark (see components/Logo.tsx / CLAUDE.md's Visual identity).
const MARK = `
  <svg viewBox="0 0 100 100" width="170" height="170" aria-hidden="true"
       fill="none" stroke="${ACCENT}" stroke-width="9" stroke-linecap="round">
    <circle cx="68" cy="36" r="20" />
    <path d="M 83 49 C 86 78, 48 96, 30 80" />
    <path d="M 12 33 Q 21 41 30 33" />
    <path d="M 88 26 L 90 14" />
  </svg>`;

const woff2 = readFileSync(
  resolve(webRoot, "node_modules/@fontsource-variable/manrope/files/manrope-latin-wght-normal.woff2"),
).toString("base64");

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
  @font-face {
    font-family: "Manrope";
    src: url(data:font/woff2;base64,${woff2}) format("woff2");
    font-weight: 100 900;
    font-display: block;
  }
  * { margin: 0; box-sizing: border-box; }
  html, body { width: ${WIDTH}px; height: ${HEIGHT}px; }
  body {
    background: ${BG};
    font-family: "Manrope", system-ui, sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 40px;
  }
  .lockup { display: flex; align-items: center; gap: 28px; }
  .wordmark {
    font-size: 116px;
    font-weight: 400;
    letter-spacing: -0.03em;
    line-height: 1;
    color: ${TEXT};
  }
  .wordmark b { font-weight: 700; color: ${ACCENT}; }
  .tagline { font-size: 40px; font-weight: 400; color: ${MUTED}; letter-spacing: -0.01em; }
</style></head><body>
  <div class="lockup">
    ${MARK}
    <div class="wordmark"><b>good</b>gorithm</div>
  </div>
  <div class="tagline">${TAGLINE}</div>
</body></html>`;

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: WIDTH, height: HEIGHT },
  deviceScaleFactor: 1,
});
await page.setContent(html, { waitUntil: "load" });
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: OUT, type: "png" });
await browser.close();

console.log(`wrote ${OUT} (${WIDTH}x${HEIGHT})`);
