import { test, expect } from "@playwright/test";

import { loginAsLearner } from "./helpers";

test("learner can log in, review a card, and open challenges", async ({ page }) => {
  await loginAsLearner(page, "Leo");

  await page.goto("/app/review");
  await expect(page.getByRole("heading", { name: /Choose words/i })).toBeVisible();
  await page.getByRole("button", { name: /^Start review$/i }).click();
  await expect(
    page.getByRole("heading", { name: /Card \d+ of|No cards due|Session complete/i }),
  ).toBeVisible({ timeout: 15000 });

  const meaning = page.getByText(/Pick the meaning/i);
  if (await meaning.isVisible().catch(() => false)) {
    await page.locator("article .grid button").first().click();
    const continueBtn = page.getByRole("button", { name: /^Continue$/i });
    if (await continueBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await continueBtn.click();
    }
    await expect(
      page.getByText(/Great pick|Not quite|Card \d+ of|Session complete|No cards due/i).first(),
    ).toBeVisible({ timeout: 10000 });
  }

  await page.goto("/app/challenges");
  await expect(page.getByRole("heading", { name: /Level-up & more/i })).toBeVisible();
});
