import { test, expect } from "@playwright/test";

import { loginAsParent } from "./helpers";

test.describe("parent flows", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsParent(page);
  });

  test("can view dashboard with learners", async ({ page }) => {
    await expect(page.getByText(/Parent corner/i)).toBeVisible();
    await expect(page.getByText(/Mia|Leo/i).first()).toBeVisible();
  });

  test("can open word lists page", async ({ page }) => {
    await page.goto("/parent/word-lists");
    await expect(page.getByRole("heading", { name: /Word lists/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Create custom list/i })).toBeVisible();
  });
});
