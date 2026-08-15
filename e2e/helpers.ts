import { expect, type Page } from "@playwright/test";

const CREDENTIALS = {
  parent: { username: "parent", password: "parent123" },
  Leo: { username: "leo", password: "leo" },
  Mia: { username: "mia", password: "mia" },
} as const;

export async function clearSession(page: Page) {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.evaluate(() => localStorage.clear());
}

async function submitLogin(
  page: Page,
  credentials: { username: string; password: string },
  expectedUrl: RegExp,
) {
  await clearSession(page);
  await page.getByLabel(/Username/i).fill(credentials.username);
  await page.getByLabel(/Password/i).fill(credentials.password);
  await page.getByRole("button", { name: /Let's go/i }).click();
  await expect(page).toHaveURL(expectedUrl);
}

export async function loginAsLearner(page: Page, name: "Leo" | "Mia" = "Leo") {
  await submitLogin(page, CREDENTIALS[name], /\/app\/home/);
}

export async function loginAsParent(page: Page) {
  await submitLogin(page, CREDENTIALS.parent, /\/parent\/dashboard/);
}

/** Remove the family word bank via API (404 when already empty is fine). */
export async function deleteFamilyWordBankIfExists(page: Page) {
  const login = await page.request.post("/api/v1/auth/login", {
    data: { username: "parent", password: "parent123" },
  });
  expect(login.ok()).toBeTruthy();
  const { access_token: accessToken } = (await login.json()) as { access_token: string };
  const response = await page.request.delete("/api/v1/word-bank", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect([200, 404]).toContain(response.status());
}
