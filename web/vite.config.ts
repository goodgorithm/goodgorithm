/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
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
