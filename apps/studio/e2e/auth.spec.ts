import { expect, test } from "@playwright/test";
import { installAuthenticatedShellMocks } from "./helpers/janua-mocks";
import { expiredMockJwt, freshMockJwt } from "./helpers/jwt";

const ACCESS_COOKIE = "ceq_access_token";
const REFRESH_COOKIE = "ceq_refresh_token";
const MOCK_JANUA_URL = "http://127.0.0.1:5999";

test.describe("Studio auth (mocked Janua)", () => {
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test("redirects unauthenticated studio routes to login with returnTo", async ({
    page,
  }) => {
    await page.goto("/workflows");
    await expect(page).toHaveURL(/\/login\?returnTo=%2Fworkflows/);
    await expect(page.getByRole("button", { name: "Enter CEQ Studio" })).toBeVisible();
  });

  test("completes mocked OAuth callback and renders the studio shell", async ({
    page,
  }) => {
    await installAuthenticatedShellMocks(page);

    await page.goto("/login?returnTo=%2F");
    await page.getByRole("button", { name: "Enter CEQ Studio" }).click();

    await expect(page).toHaveURL(/\/auth\/callback/, { timeout: 10_000 });
    await expect(page).toHaveURL(/http:\/\/127\.0\.0\.1:5801\/(\?|$)/, {
      timeout: 15_000,
    });
    await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
    await expect(page.getByText("Signal acquired.")).toBeVisible();

    const cookies = await page.context().cookies();
    expect(cookies.some((cookie) => cookie.name === ACCESS_COOKIE)).toBe(true);
    expect(cookies.some((cookie) => cookie.name === REFRESH_COOKIE)).toBe(true);
  });

  test("surfaces Janua token exchange failures on callback", async ({ page }) => {
    await page.goto(
      `${MOCK_JANUA_URL}/api/v1/oauth/authorize?client_id=ceq-studio-e2e&redirect_uri=${encodeURIComponent(
        "http://127.0.0.1:5801/auth/callback"
      )}&response_type=code&scope=openid+profile+email&state=%2F&force_error=1`
    );

    await expect(page).toHaveURL(/\/auth\/callback/, { timeout: 10_000 });
    await expect(page.getByText("Authentication Error")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/Token exchange failed|invalid_client/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Try Again" })).toBeVisible();
  });

  test("clears session cookies on logout", async ({ page }) => {
    await installAuthenticatedShellMocks(page);

    await page.goto("/login?returnTo=%2F");
    await page.getByRole("button", { name: "Enter CEQ Studio" }).click();
    await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible({
      timeout: 15_000,
    });

    await page.getByRole("button", { name: "Account" }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();

    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });

    const session = await page.request.get("/api/auth/session");
    expect(session.status()).toBe(401);
  });

  test("refreshes expired access tokens via refresh cookie", async ({
    page,
    context,
  }) => {
    await context.addCookies([
      {
        name: ACCESS_COOKIE,
        value: expiredMockJwt(),
        domain: "127.0.0.1",
        path: "/",
        httpOnly: true,
        secure: false,
        sameSite: "Lax",
      },
      {
        name: REFRESH_COOKIE,
        value: "e2e-refresh-token",
        domain: "127.0.0.1",
        path: "/",
        httpOnly: true,
        secure: false,
        sameSite: "Lax",
      },
    ]);

    const session = await page.request.get("/api/auth/session");
    expect(session.ok()).toBe(true);

    const payload = await session.json();
    expect(payload.access_token).toBeTruthy();
    expect(payload.access_token).not.toBe(expiredMockJwt());
    expect(payload.user?.email).toBe("studio-e2e@madfam.io");
  });

  test("session bootstrap returns user for valid access cookie", async ({
    context,
    page,
  }) => {
    const accessToken = freshMockJwt();

    await context.addCookies([
      {
        name: ACCESS_COOKIE,
        value: accessToken,
        domain: "127.0.0.1",
        path: "/",
        httpOnly: true,
        secure: false,
        sameSite: "Lax",
      },
    ]);

    const session = await page.request.get("/api/auth/session");
    expect(session.ok()).toBe(true);

    const payload = await session.json();
    expect(payload.user.email).toBe("studio-e2e@madfam.io");
    expect(payload.access_token).toBe(accessToken);
  });
});
