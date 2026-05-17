/**
 * Deployed-environment smoke tests. Runs against whatever URL you point it at.
 *
 * Local:
 *   npm run test:e2e -- deployed-smoke.spec.ts
 *
 * Live Vercel + Render:
 *   PLAYWRIGHT_BASE_URL=https://thrive-record-hub.vercel.app \
 *     npx playwright test deployed-smoke.spec.ts
 *
 * What it verifies:
 *   1. Backend `/healthz` responds with the expected tenant + agent counts.
 *   2. Dashboard root loads and redirects to /dashboard.
 *   3. JARVIS page renders the voice orb.
 *   4. Setup wizard renders 8 steps.
 *   5. Agents registry lists at least one specialist.
 *
 * This is the script you run *after* the Render + Vercel deploys finish to
 * prove the wiring is correct end-to-end. Run it from your Mac — Playwright
 * already lives in this directory.
 */

import { test, expect } from "@playwright/test";

const API_PATH = process.env.PLAYWRIGHT_API_PATH ?? "/api/avengers";

test.describe("Deployed environment — smoke", () => {
  test("backend /healthz reports tenants + agents + connectors", async ({ request, baseURL }) => {
    const res = await request.get(`${baseURL}${API_PATH}/healthz`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe("ok");
    expect(body.tenants).toBeGreaterThanOrEqual(3);
    expect(body.agents).toBeGreaterThanOrEqual(9);
    expect(body.connectors_known.length).toBeGreaterThan(0);
  });

  test("dashboard root redirects and renders the hero", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByText(/morning brief/i)).toBeVisible();
  });

  test("JARVIS page renders the voice orb", async ({ page }) => {
    await page.goto("/jarvis");
    await expect(page.getByRole("button", { name: /jarvis voice/i })).toBeVisible();
    await expect(page.getByText(/JARVIS · personal AI for Cap Brij/i)).toBeVisible();
  });

  test("setup wizard renders 8 steps", async ({ page }) => {
    await page.goto("/setup");
    await expect(page.getByRole("heading", { name: /jarvis in 8 steps/i })).toBeVisible();
    for (let i = 1; i <= 8; i++) {
      await expect(page.getByText(new RegExp(`^${i}\\.`)).first()).toBeVisible();
    }
  });

  test("agents page lists at least one specialist", async ({ page }) => {
    await page.goto("/agents");
    await expect(page.getByRole("heading", { name: /agent registry/i })).toBeVisible();
    await expect(
      page.getByText(/meetings|markets|security|research|content|operations|catalog|inventory|reconciliation/i).first(),
    ).toBeVisible({ timeout: 10_000 });
  });
});
