import { describe, expect, it } from "vitest";

// Hexes copied from src/theme.css (like e2e/theme.spec.ts hardcodes
// --color-bg). A cheap regression guard on the --card-tint-* pairs: a tint
// that drops text below WCAG AA, or that strays far enough from the base
// surface to stop being "barely there", fails here. No axe harness exists
// otherwise.
const THEME = {
  light: {
    text: "#16211b",
    textSecondary: "#5b665f",
    surface: "#ffffff",
    tints: ["#f3f7f4", "#f8f5f0", "#f6f6f3", "#fdf3f0", "#f3f6f3"],
  },
  dark: {
    text: "#ecf3ef",
    textSecondary: "#9fada6",
    surface: "#19221e",
    tints: ["#19231e", "#21201c", "#1e211e", "#231d1c", "#1b211d"],
  },
} as const;

function channel(v: number): number {
  const c = v / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  return (
    0.2126 * channel((n >> 16) & 0xff) +
    0.7152 * channel((n >> 8) & 0xff) +
    0.0722 * channel(n & 0xff)
  );
}

function contrast(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

describe.each(["light", "dark"] as const)("card tints — %s theme", (mode) => {
  const t = THEME[mode];

  it.each(t.tints)("body text clears WCAG AA (4.5:1) on %s", (tint) => {
    expect(contrast(t.text, tint)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(t.tints)("secondary text clears WCAG AA (4.5:1) on %s", (tint) => {
    expect(contrast(t.textSecondary, tint)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(t.tints)("%s is barely-there against the base surface (<1.1:1)", (tint) => {
    expect(contrast(tint, t.surface)).toBeLessThan(1.1);
  });
});
