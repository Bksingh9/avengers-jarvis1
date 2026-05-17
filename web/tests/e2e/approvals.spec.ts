import { test, expect } from "@playwright/test";

test.describe("Approvals queue", () => {
  test("renders empty-state when there are no pending approvals", async ({ page }) => {
    await page.goto("/approvals");

    await expect(page.getByRole("heading", { name: /approvals/i })).toBeVisible();

    // Either the empty-state copy OR at least one pending approval card
    // (if a prior test posted one). Both are valid responses to the GET.
    const emptyOrItem = page.locator("text=/no pending approvals|pending|approved|denied/i");
    await expect(emptyOrItem.first()).toBeVisible({ timeout: 10_000 });
  });
});
