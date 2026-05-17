import { test, expect } from "@playwright/test";

test.describe("Dashboard", () => {
  test("loads, shows the hero, and streams in section cards", async ({ page }) => {
    await page.goto("/dashboard");

    // Sidebar is always visible on desktop viewport.
    await expect(page.getByRole("link", { name: /today/i })).toBeVisible();

    // Hero copy appears either as "Composing your brief" (running) or
    // "Today, in one screen." (done). Either is acceptable as the page
    // auto-runs the brief on mount.
    await expect(
      page.getByText(/composing your brief|today, in one screen|ready when you are/i),
    ).toBeVisible({ timeout: 5_000 });

    // The "Run brief now" button is present and labelled correctly.
    await expect(page.getByRole("button", { name: /run brief|streaming/i })).toBeVisible();

    // Within 30s, at least one specialist section should reach a terminal
    // status badge — ok / error / partial.
    await expect(
      page.getByText(/^(ok|error|partial)$/).first(),
    ).toBeVisible({ timeout: 30_000 });
  });

  test("command palette opens with ⌘K", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "keyboard shortcuts vary by browser");
    await page.goto("/dashboard");
    await page.keyboard.press("Meta+K");
    await expect(page.getByPlaceholder(/type a command/i)).toBeVisible();
    await page.keyboard.press("Escape");
  });
});
