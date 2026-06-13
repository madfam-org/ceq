import type { Page } from "@playwright/test";

/** Keep authenticated shell tests independent from a live ceq-api. */
export async function installStudioApiMocks(page: Page): Promise<void> {
  await page.route("**/api/proxy/v1/workflows/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [],
        total: 0,
        skip: 0,
        limit: 20,
      }),
    });
  });

  await page.route("**/api/proxy/v1/jobs/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        jobs: [],
        total: 0,
        skip: 0,
        limit: 10,
      }),
    });
  });

  await page.route("**/api/proxy/v1/credits/balance**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        balance: 100,
        currency: "credits",
      }),
    });
  });

  await page.route("**/api/proxy/health**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", message: "e2e mock" }),
    });
  });
}
