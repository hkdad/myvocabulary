import { test, expect } from "@playwright/test";

import { loginAsLearner } from "./helpers";

test.describe("learner flows", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsLearner(page, "Leo");
  });

  test("can open word lists and create form", async ({ page }) => {
    await page.goto("/app/lists");
    await expect(page.getByRole("heading", { name: "Word lists" })).toBeVisible();
    await expect(page.getByPlaceholder("e.g. Week 5 spelling")).toBeVisible();
    await expect(page.getByRole("button", { name: /Create list/i })).toBeVisible();
  });

  test("can open dictionary and search", async ({ page }) => {
    await page.goto("/app/dictionary");
    await expect(page.getByRole("heading", { name: /Look up a word/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Today's challenge/i })).toBeVisible();
    const search = page.getByPlaceholder(/elephant|aurora|happy/i);
    await search.fill("hello");
    await page.getByRole("button", { name: /Search/i }).click();
    await expect(page.getByText(/hello/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test("can open review session", async ({ page }) => {
    await page.goto("/app/review");
    await expect(page.getByRole("heading", { name: /Choose words/i })).toBeVisible();
    await page.getByRole("button", { name: /^Start review$/i }).click();
    await expect(
      page.getByRole("heading", { name: /Card \d+ of|No cards due|Session complete/i }),
    ).toBeVisible({ timeout: 15000 });
  });

  test("can open dictation setup", async ({ page }) => {
    await page.goto("/app/dictation");
    await expect(page.getByRole("heading", { name: /Listen and spell/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Start dictation/i })).toBeVisible();
  });

  test("can open listen and pick setup", async ({ page }) => {
    await page.goto("/app/dictation/pick");
    await expect(page.getByRole("heading", { name: /Listen and pick/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Start Listen & Pick/i })).toBeVisible();
  });

  test("can open stats and mistakes link when present", async ({ page }) => {
    await page.goto("/app/stats");
    await expect(page.getByRole("heading", { name: "Stats" })).toBeVisible();
    const mistakesLink = page.getByRole("link", { name: /Review mistakes/i });
    if (await mistakesLink.isVisible().catch(() => false)) {
      await mistakesLink.click();
      await expect(page).toHaveURL(/\/app\/review\?mistakes=1/);
    }
  });
});
