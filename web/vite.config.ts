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
        description: "An algorithmic feed of positive, uplifting public social posts.",
        start_url: "/",
        display: "standalone",
        background_color: "#ffffff",
        theme_color: "#111111",
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
