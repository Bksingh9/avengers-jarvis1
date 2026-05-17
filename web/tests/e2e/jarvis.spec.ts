import { test, expect } from "@playwright/test";

test.describe("JARVIS", () => {
  test("page loads, voice orb renders, suggestions are clickable", async ({ page }) => {
    await page.goto("/jarvis");

    await expect(page.getByRole("heading", { name: /talk to your operating system/i })).toBeVisible();
    await expect(page.getByText(/JARVIS · personal AI for Cap Brij/i)).toBeVisible();

    // Voice orb button is present (aria-label = "JARVIS voice")
    await expect(page.getByRole("button", { name: /jarvis voice/i })).toBeVisible();

    // One of the empty-state suggestions is clickable.
    const suggestion = page.getByRole("button", { name: /what broke overnight/i });
    await expect(suggestion).toBeVisible();
  });

  test("typing a question sends it and JARVIS replies", async ({ page }) => {
    await page.goto("/jarvis");
    const composer = page.getByPlaceholder(/type or hold the orb/i);
    await composer.fill("ping");
    await composer.press("Enter");

    // Cap's bubble shows up immediately.
    await expect(page.getByText("ping").first()).toBeVisible({ timeout: 5_000 });
    // JARVIS reply arrives within 30s — at least one citation chip appears.
    await expect(page.locator("text=/connector·tool|seed|demo/").first()).toBeVisible({
      timeout: 30_000,
    });
  });
});

test.describe("Setup wizard", () => {
  test("renders 8 steps and the progress bar", async ({ page }) => {
    await page.goto("/setup");
    await expect(page.getByRole("heading", { name: /jarvis in 8 steps/i })).toBeVisible();

    // Count step cards by looking for the numbered prefixes "1.", "2.", … "8."
    for (let i = 1; i <= 8; i++) {
      await expect(page.getByText(new RegExp(`^${i}\\.`)).first()).toBeVisible();
    }

    // Initial progress is 0%
    await expect(page.getByText(/0 of 8 steps complete/i)).toBeVisible();
  });
});
