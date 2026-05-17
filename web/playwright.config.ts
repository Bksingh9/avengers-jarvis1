import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config — covers the dashboard end-to-end against a running
 * Next.js dev server. The backend (FastAPI on :8080) must be running
 * separately; you can either:
 *   uvicorn avengers.api.__main__:app --port 8080      (local)
 *   PLAYWRIGHT_BASE_URL=https://<vercel-url> npm run test:e2e   (live site)
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["html"], ["github"]] : "list",
  timeout: 60_000, // SSE briefs can take ~30s

  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },

  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],

  // Start the Next dev server automatically when running locally. Skip when
  // PLAYWRIGHT_BASE_URL points at a live deployment.
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: "npm run dev",
        url: "http://localhost:3000",
        reuseExistingServer: !process.env.CI,
        timeout: 60_000,
      },
});
