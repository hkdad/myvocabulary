import { test, expect } from "@playwright/test";

import { loginAsLearner } from "./helpers";

const SCREENSHOT_DIR = "artifacts/screenshots";

const FIXTURE_WORD = "e2eline";
const FIXTURE_ZH = "錯誤翻譯";

test.describe("clear translation", () => {
  test("learner clears cached zh from dictionary WordCard", async ({ page }) => {
    await loginAsLearner(page, "Leo");
    await page.goto(`/app/dictionary/${FIXTURE_WORD}`);

    await expect(page.getByText(FIXTURE_ZH)).toBeVisible();
    await expect(page.getByRole("button", { name: /Clear translation/i })).toBeVisible();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/clear-translation-before.png`,
      fullPage: true,
    });

    await page.getByRole("button", { name: /Clear translation/i }).click();

    await expect(page.getByText(FIXTURE_ZH)).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Clear translation/i })).toHaveCount(0);
    await expect(page.getByText(/Cleared\. We'll translate again next time\./i)).toBeVisible();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/clear-translation-after.png`,
      fullPage: true,
    });

    const login = await page.request.post("/api/v1/auth/login", {
      data: { username: "leo", password: "leo" },
    });
    expect(login.ok()).toBeTruthy();
    const { access_token: token } = (await login.json()) as { access_token: string };
    const entry = await page.request.get(`/api/v1/dictionary/words/${FIXTURE_WORD}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(entry.ok()).toBeTruthy();
    const body = (await entry.json()) as { definition_zh_hant: string | null };
    expect(body.definition_zh_hant).toBeNull();
  });

  test("parent can clear cached zh via API", async ({ page }) => {
    const fixtureWord = "e2elineparent";
    const parentLogin = await page.request.post("/api/v1/auth/login", {
      data: { username: "parent", password: "parent123" },
    });
    expect(parentLogin.ok()).toBeTruthy();
    const { access_token: parentToken } = (await parentLogin.json()) as {
      access_token: string;
    };
    const parentAuth = { Authorization: `Bearer ${parentToken}` };

    const learnerLogin = await page.request.post("/api/v1/auth/login", {
      data: { username: "leo", password: "leo" },
    });
    expect(learnerLogin.ok()).toBeTruthy();
    const { access_token: learnerToken } = (await learnerLogin.json()) as {
      access_token: string;
    };
    const learnerAuth = { Authorization: `Bearer ${learnerToken}` };

    const before = await page.request.get(`/api/v1/dictionary/words/${fixtureWord}`, {
      headers: learnerAuth,
    });
    expect(before.ok()).toBeTruthy();
    const entry = (await before.json()) as { id: number; definition_zh_hant: string | null };
    expect(entry.definition_zh_hant).toBe(FIXTURE_ZH);

    const cleared = await page.request.delete(
      `/api/v1/dictionary/entries/${entry.id}/zh-hant`,
      { headers: parentAuth },
    );
    expect(cleared.ok()).toBeTruthy();
    expect(await cleared.json()).toEqual({
      id: entry.id,
      definition_zh_hant: null,
    });

    const after = await page.request.get(`/api/v1/dictionary/words/${fixtureWord}`, {
      headers: learnerAuth,
    });
    expect(after.ok()).toBeTruthy();
    expect((await after.json()).definition_zh_hant).toBeNull();
  });
});
