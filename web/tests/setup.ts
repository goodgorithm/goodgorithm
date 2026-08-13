import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

// Explicit cleanup - RTL's auto-cleanup only self-registers when it detects
// a global afterEach, but tests here import afterEach explicitly rather than
// relying on vitest's globals mode.
afterEach(cleanup);

// Node 22+'s own native `localStorage` global occupies the `localStorage`
// property before jsdom's environment can install its real implementation,
// and resolves to `undefined` without the (unused here) --localstorage-file
// flag - so any code under test that touches `localStorage` silently no-ops.
// Replace it with a working in-memory polyfill.
if (typeof globalThis.localStorage === "undefined") {
  const store = new Map<string, string>();
  const polyfill: Storage = {
    getItem: (key) => (store.has(key) ? (store.get(key) ?? null) : null),
    setItem: (key, value) => void store.set(key, String(value)),
    removeItem: (key) => void store.delete(key),
    clear: () => void store.clear(),
    key: (index) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
  };
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: polyfill });
}

// jsdom doesn't implement matchMedia at all - anything under test that reads
// prefers-color-scheme (e.g. useNativeStatusBar.ts, issue #9) throws without
// this. Static (always non-matching, no-op listeners): nothing here needs
// to simulate an actual media-feature change, just not crash.
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
