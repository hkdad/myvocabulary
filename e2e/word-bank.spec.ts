import { test, expect } from "@playwright/test";

import { loginAsParent, deleteFamilyWordBankIfExists } from "./helpers";

const LEVEL_MIX_CSV = `word,definition,level,category
alpha,First word,A1,General
beta,Second word,B1,Science
`;

test.describe.configure({ mode: "serial" });

test.describe("word bank browser", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsParent(page);
    await deleteFamilyWordBankIfExists(page);
    await page.goto("/parent/word-lists");

    await page.locator('input[type="file"]').setInputFiles({
      name: "level-mix.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(LEVEL_MIX_CSV),
    });
    await expect(page.getByText(/Imported/i)).toBeVisible({ timeout: 15000 });
  });

  test("level filter options match levels in the bank", async ({ page }) => {
    await page.goto("/parent/word-bank");
    await expect(page.getByRole("heading", { name: /Family word bank/i })).toBeVisible();

    const levelSelect = page.getByLabel("Filter by level");
    await expect(levelSelect.locator("option")).toHaveText(["All levels", "A1", "B1"]);
    await expect(levelSelect.locator("option", { hasText: "A2" })).toHaveCount(0);
  });

  test("category filter options match categories in the bank", async ({ page }) => {
    await page.goto("/parent/word-bank");

    const categorySelect = page.getByLabel("Filter by category");
    await expect(categorySelect.locator("option")).toHaveText([
      "All categories",
      "General",
      "Science",
    ]);
    await expect(categorySelect.locator("option", { hasText: "Food" })).toHaveCount(0);
  });

  test("level filter narrows the word table", async ({ page }) => {
    await page.goto("/parent/word-bank");
    await expect(page.getByText(/Showing 2 of 2 matching words/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(page.locator("table tbody tr", { hasText: "alpha" })).toBeVisible();
    await expect(page.locator("table tbody tr", { hasText: "beta" })).toBeVisible();

    await page.getByLabel("Filter by level").selectOption("B1");
    await expect(page.getByText(/Showing 1 of 1 matching words/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(page.locator("table tbody tr", { hasText: "beta" })).toBeVisible();
    await expect(page.locator("table tbody tr", { hasText: "alpha" })).toHaveCount(0);
  });
});

test.describe("word bank upload validation", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsParent(page);
    await page.goto("/parent/word-lists");
  });

  test("blocks csv missing level column before upload", async ({ page }) => {
    await page.locator('input[type="file"]').setInputFiles({
      name: "bad.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("word,definition,category\napple,Fruit,Food\n"),
    });
    await expect(page.getByText(/Missing required column: level/i)).toBeVisible({
      timeout: 5000,
    });
  });
});
