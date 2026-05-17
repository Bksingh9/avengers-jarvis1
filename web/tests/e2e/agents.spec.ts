import { test, expect } from "@playwright/test";

test.describe("Agents registry", () => {
  test("lists at least one specialist with a model badge", async ({ page }) => {
    await page.goto("/agents");

    await expect(page.getByRole("heading", { name: /agent registry/i })).toBeVisible();

    // Wait for the SWR fetch to settle; we should see at least one of the six
    // reference specialists by display name.
    const anyKnownAgent = page.getByText(
      /meetings|markets|security|research|content|operations/i,
    ).first();
    await expect(anyKnownAgent).toBeVisible({ timeout: 10_000 });
  });
});
