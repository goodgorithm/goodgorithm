import { defineConfig, devices } from "@playwright/test";

// Documented pre-push/pre-merge check (see CONTRIBUTING.md), not a CI gate -
// multi-browser E2E is slower and more flake-prone than Vitest, and this
// project doesn't have a device farm for real mobile WebViews (Capacitor
// iOS/Android), so this only covers desktop Chromium/Firefox/WebKit. See
// issue #69.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
  // Both processes are started once for the whole run (not per-project) and
  // torn down after - reuses the exact mock backend the run-web skill uses
  // (e2e/mock-api.mjs), so there's one canonical mock, not two to keep in
  // sync. reuseExistingServer lets a contributor leave `npm run dev`/the
  // mock running locally across repeated `npx playwright test` invocations
  // instead of a slow restart every time (never true in CI, which starts
  // clean regardless of the env var since forbidOnly's pattern doesn't
  // apply here - explicit !process.env.CI is what actually gates it).
  webServer: [
    {
      command: "node e2e/mock-api.mjs 4100",
      url: "http://localhost:4100/health",
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npm run dev",
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
      env: { VITE_API_BASE_URL: "http://localhost:4100" },
    },
  ],
});
