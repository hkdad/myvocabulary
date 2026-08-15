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
term11,Meaning eleven,A2,General
term12,Meaning twelve,A2,General
advanced,Hard word,B1,Science
`;

test.describe.configure({ mode: "serial" });

async function completeChallengeViaApi(page: import("@playwright/test").Page) {
  const login = await page.request.post("/api/v1/auth/login", {
    data: { username: "leo", password: "leo" },
  });
  expect(login.ok()).toBeTruthy();
  const { access_token: token } = (await login.json()) as { access_token: string };
  const auth = { Authorization: `Bearer ${token}` };

  const mix = await page.request.get("/api/v1/loop/today", { headers: auth });
  expect(mix.ok()).toBeTruthy();
  const cards = (await mix.json()).cards as { id: number }[];
  expect(cards.length).toBeGreaterThan(0);

  // Listen & Pick first, then recognition review — both required to complete the day.
  const dictation = await page.request.post("/api/v1/dictation/sessions", {
    headers: auth,
    data: { source: "daily_challenge", mode: "choice", max_words: 30 },
  });
  expect(dictation.ok()).toBeTruthy();
  const sessionId = (await dictation.json()).id as number;
  const totalWords = (await dictation.json()).total_words as number;
  for (let i = 0; i < totalWords * 4; i += 1) {
    const prompt = await page.request.get(`/api/v1/dictation/sessions/${sessionId}/next`, {
      headers: auth,
    });
    if (!prompt.ok()) {
      break;
    }
    const data = await prompt.json();
    if (data.session_complete) {
      break;
    }
    for (const choice of data.choices ?? []) {
      const answer = await page.request.post(`/api/v1/dictation/sessions/${sessionId}/answer`, {
        headers: auth,
        data: { answer: choice, hint_used: false },
      });
      if (!answer.ok()) {
        continue;
      }
      const result = await answer.json();
      if (result.session_complete) {
        break;
      }
      if (result.is_correct) {
        break;
      }
    }
  }

  for (const card of cards) {
    const answer = await page.request.post(`/api/v1/reviews/${card.id}/answer`, {
      headers: auth,
      data: { quality: 4 },
    });
    expect(answer.ok()).toBeTruthy();
  }

  const srs = await page.request.post("/api/v1/loop/today/srs-complete", { headers: auth });
  expect(srs.ok()).toBeTruthy();
  expect((await srs.json()).srs_completed).toBeTruthy();
  expect((await srs.json()).completed).toBeTruthy();

  const progress = await page.request.get("/api/v1/loop/progress", { headers: auth });
  expect(progress.ok()).toBeTruthy();
  expect((await progress.json()).daily_challenge_completed).toBeTruthy();
}

test.describe("learning loop", () => {
  test.beforeEach(async ({ page }) => {
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
  });

  test("parent sees bank import summary", async ({ page }) => {
    await expect(page.getByText(/words in bank/i)).toBeVisible();
  });

  test("kid daily challenge has start challenge and no mark done", async ({ page }) => {
    await loginAsLearner(page, "Leo");
    await expect(page.getByRole("heading", { name: /Daily challenge/i })).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByRole("link", { name: /full stats/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Mark done/i })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /Start challenge/i })).toBeVisible();
    await expect(page.getByText(/Two steps: Listen & Pick, then recognition review/i).first()).toBeVisible();
  });

  test("kid completes daily challenge via Listen & Pick then recognition", async ({ page }) => {
    await loginAsLearner(page, "Leo");
    await expect(page.getByRole("heading", { name: /Daily challenge/i })).toBeVisible({
      timeout: 15000,
    });
    await page.getByRole("link", { name: /Start challenge/i }).click();
    await expect(page).toHaveURL(/\/app\/challenge/);
    await expect(page.getByText(/Daily challenge · Step 1 · Listen & Pick/i)).toBeVisible({
      timeout: 15000,
    });

    await completeChallengeViaApi(page);

    await page.goto("/app/home");
    await expect(page.getByText(/Completed today/i)).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("link", { name: /Practice again/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Mark done/i })).toHaveCount(0);
  });

  test("review and dictation pickers include today's challenge", async ({ page }) => {
    await loginAsLearner(page, "Leo");
    await page.goto("/app/review");
    await expect(page.getByLabel(/Word source/i)).toBeVisible({ timeout: 10000 });
    await expect(page.getByLabel(/Word source/i).locator("option", { hasText: /Today/i })).toHaveCount(
      1,
    );

    await page.goto("/app/dictation");
    await expect(page.getByLabel(/Choose words/i)).toBeVisible({ timeout: 10000 });
    await expect(
      page.getByLabel(/Choose words/i).locator("option", { hasText: /Today/i }),
    ).toHaveCount(1);
  });

  test("parent dashboard shows strength buckets", async ({ page }) => {
    await loginAsLearner(page, "Leo");
    await expect(page.getByRole("heading", { name: /Daily challenge/i })).toBeVisible({
      timeout: 15000,
    });
    await loginAsParent(page);
    await expect(page.getByText(/Learning/i).first()).toBeVisible();
    await expect(page.getByText(/Familiar/i).first()).toBeVisible();
    await expect(page.getByText(/Mastered/i).first()).toBeVisible();
  });

  test("A2 learner daily mix excludes B1 words", async ({ page }) => {
    await loginAsLearner(page, "Leo");
    await expect(page.getByRole("heading", { name: /Daily challenge/i })).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByText(/advanced/i)).not.toBeVisible();
  });
});
