/// <reference types="vitest/config" />
import { defineConfig, type Plugin, type ResolvedConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// Small build/dev HTML transforms that shorten the chain before the first
// paint (issue #110). No runtime dependency -- this is the "tiny Vite
// transformIndexHtml hook" the issue calls for. See the wiki's Web
// Internals page.
function prepaintOptimizations(): Plugin {
  let apiBase = "";
  return {
    name: "prepaint-optimizations",
    configResolved(config: ResolvedConfig) {
      // Mode-aware: picks up VITE_API_BASE_URL from .env.<mode>, the CI
      // environment, or Playwright's injected webServer env alike.
      apiBase = config.env.VITE_API_BASE_URL ?? "";
    },
    transformIndexHtml: {
      order: "post",
      handler(html, ctx) {
        if (!apiBase) {
          throw new Error(
            "VITE_API_BASE_URL is required to build the index.html preconnect + feed-bootstrap tags",
          );
        }

        // 1. Inject the api/ origin into the preconnect links and the
        //    inline feed-bootstrap <script> (both in index.html). Runs in
        //    dev and build.
        html = html.replaceAll("__API_BASE__", apiBase);

        // 2. Stop the app's own stylesheet from render-blocking the first
        //    paint -- index.html's inline <style> already covers the shell.
        //    Only present in a build; dev injects CSS via JS.
        html = html.replace(
          /<link rel="stylesheet"([^>]*)>/,
          (_m, attrs: string) =>
            `<link rel="stylesheet"${attrs} media="print" onload="this.media='all'">` +
            `<noscript><link rel="stylesheet"${attrs}></noscript>`,
        );

        // 3. Build only: preload the entry chunk and the Latin Manrope
        //    subset (the one the wordmark + English body text use) from
        //    their hashed names.
        if (ctx.bundle) {
          const entry = Object.values(ctx.bundle).find(
            (c) => c.type === "chunk" && c.isEntry,
          );
          if (entry) {
            html = html.replace(
              '<script type="module"',
              `<link rel="modulepreload" href="/${entry.fileName}"><script type="module"`,
            );
          }
          const latinFont = Object.keys(ctx.bundle).find((f) =>
            /manrope-latin-wght-normal-[^/]*\.woff2$/.test(f),
          );
          if (latinFont) {
            html = html.replace(
              "</head>",
              `<link rel="preload" as="font" type="font/woff2" href="/${latinFont}" crossorigin></head>`,
            );
          }
        }

        return html;
      },
    },
  };
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    prepaintOptimizations(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        id: "/",
        name: "Goodgorithm",
        short_name: "Goodgorithm",
        // Matches index.html's meta description/og:description/twitter:description
        // and the JSON-LD description exactly - keep all four in sync by
        // hand if this copy ever changes.
        description:
          "Goodgorithm surfaces genuinely uplifting posts from across the open social web — a free, open-source feed built to counter doomscrolling, not feed it.",
        start_url: "/",
        display: "standalone",
        background_color: "#121815",
        theme_color: "#1f9d55",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/icons/icon-512-maskable.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico}"],
        // Without this, Workbox's NavigationRoute (bound to index.html)
        // intercepts *every* browser navigation with no exceptions -
        // including a direct visit to /robots.txt or /sitemap.xml, which
        // would otherwise silently serve the cached SPA shell instead of
        // the real file, to any visitor who already has the service worker
        // installed. See the wiki's Web Internals page for the full story.
        navigateFallbackDenylist: [/^\/robots\.txt$/, /^\/sitemap\.xml$/],
        // Deliberately no runtimeCaching entry for the api/ origin. The
        // default generateSW strategy only precaches build output (matched
        // above) and never intercepts cross-origin fetches unless a rule is
        // added for them - so the correct move here is *not adding one*,
        // not writing a NetworkOnly rule. A live-ranked feed silently
        // serving cached/stale posts while offline would misrepresent
        // itself, which cuts against the project's transparency stance.
        // FeedError (see components/FeedStatus.tsx) is what users see
        // offline instead - don't "helpfully" add caching here without
        // re-litigating that decision.
      },
    }),
  ],
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
