import { test, expect } from "@playwright/test";

import { loginAsLearner, loginAsParent } from "./helpers";

const FIXTURE_CSV = `word,definition,level,category
apple,A round fruit,A2,Food
banana,Yellow fruit,A2,Food
cat,A small animal,A2,Animals / nature
dog,A loyal pet,A2,Animals / nature
easy,Easy word,A2,General
term6,Meaning six,A2,General
term7,Meaning seven,A2,General
term8,Meaning eight,A2,General
term9,Meaning nine,A2,General
term10,Meaning ten,A2,General
`;

function normalizeDefinition(text: string): string {
  return text.trim().toLowerCase().replace(/\s+/g, " ");
}

async function leoAuth(page: import("@playwright/test").Page) {
  const login = await page.request.post("/api/v1/auth/login", {
    data: { username: "leo", password: "leo" },
  });
  expect(login.ok()).toBeTruthy();
  const { access_token: token } = (await login.json()) as { access_token: string };
  return { Authorization: `Bearer ${token}` };
}

async function seedDueCards(page: import("@playwright/test").Page) {
  await loginAsParent(page);
  await page.goto("/parent/word-lists");
  await expect(page.getByRole("heading", { name: /Word lists/i })).toBeVisible({
    timeout: 15000,
  });
  const fileInput = page.locator('input[type="file"]');
  await expect(fileInput).toBeAttached({ timeout: 15000 });
  await fileInput.setInputFiles({
    name: "fixture-bank.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(FIXTURE_CSV),
  });
  await expect(page.getByText(/Imported/i)).toBeVisible({ timeout: 15000 });

  const auth = await leoAuth(page);
  const mix = await page.request.get("/api/v1/loop/today", { headers: auth });
  expect(mix.ok()).toBeTruthy();

  const due = await page.request.get("/api/v1/reviews/due", { headers: auth });
  expect(due.ok()).toBeTruthy();
  const cards = (await due.json()).cards as Array<{
    dictionary_entry: { definition: string };
  }>;
  expect(cards.length).toBeGreaterThan(0);
}

async function getFirstDueDefinition(page: import("@playwright/test").Page) {
  const auth = await leoAuth(page);
  const due = await page.request.get("/api/v1/reviews/due", { headers: auth });
  expect(due.ok()).toBeTruthy();
  const cards = (await due.json()).cards as Array<{
    dictionary_entry: { definition: string };
  }>;
  expect(cards.length).toBeGreaterThan(0);
  return cards[0].dictionary_entry.definition;
}

test.describe("SRS review", () => {
  test.beforeEach(async ({ page }) => {
    await seedDueCards(page);
  });

  test("wrong pick shows feedback and waits for Continue before advancing", async ({ page }) => {
    const correctDefinition = await getFirstDueDefinition(page);
    await loginAsLearner(page, "Leo");

    await page.goto("/app/review");
    await expect(page.getByRole("heading", { name: /Choose words/i })).toBeVisible();
    await page.getByLabel(/Word source/i).selectOption("all");
    await page.getByRole("button", { name: /^Start review$/i }).click();
    await expect(page.getByRole("heading", { name: /Card 1 of/i })).toBeVisible({
      timeout: 15000,
    });

    const correctNorm = normalizeDefinition(correctDefinition);
    const choices = page.locator("article .grid button");
    const choiceCount = await choices.count();
    expect(choiceCount).toBeGreaterThan(1);

    let clickedWrong = false;
    for (let i = 0; i < choiceCount; i += 1) {
      const text = await choices.nth(i).innerText();
      const firstLine = text.split("\n")[0];
      if (normalizeDefinition(firstLine) !== correctNorm) {
        await choices.nth(i).click();
        clickedWrong = true;
        break;
      }
    }
    expect(clickedWrong).toBeTruthy();

    await expect(page.getByText(/Not quite — check the meaning above/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /^Continue$/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Card 1 of/i })).toBeVisible();

    await page.waitForTimeout(900);
    await expect(page.getByRole("heading", { name: /Card 1 of/i })).toBeVisible();

    await page.getByRole("button", { name: /^Continue$/i }).click();

    await expect(
      page.getByRole("heading", { name: /Card 2 of|Session complete/i }),
    ).toBeVisible({ timeout: 10000 });
  });
});
