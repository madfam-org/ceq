import { defineConfig, devices } from "@playwright/test";
const HOST = "127.0.0.1";
const STUDIO_PORT = 5801;
const MOCK_JANUA_PORT = 5999;
const BASE_URL = `http://${HOST}:${STUDIO_PORT}`;
const MOCK_JANUA_URL = `http://${HOST}:${MOCK_JANUA_PORT}`;

const studioServerEnv = {
  HOSTNAME: HOST,
  PORT: String(STUDIO_PORT),
  JANUA_CLIENT_SECRET: "e2e-janua-client-secret",
  NEXT_PUBLIC_JANUA_CLIENT_ID: "ceq-studio-e2e",
  NEXT_PUBLIC_JANUA_URL: MOCK_JANUA_URL,
  NEXT_PUBLIC_API_URL: "http://127.0.0.1:5800",
  NEXT_PUBLIC_WS_URL: "ws://127.0.0.1:5800",
};

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["list"], ["github"]] : [["list"]],
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "node e2e/mock-janua-server.mjs",
      url: `${MOCK_JANUA_URL}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      env: {
        MOCK_JANUA_HOST: HOST,
        MOCK_JANUA_PORT: String(MOCK_JANUA_PORT),
      },
    },
    {
      // Use next dev so NEXT_PUBLIC_* and server routes pick up mock Janua at
      // runtime. Standalone output bakes client env at build time.
      command: "pnpm exec next dev -p 5801 -H 127.0.0.1",
      url: `${BASE_URL}/login`,
      reuseExistingServer: false,
      timeout: 180_000,
      env: studioServerEnv,
    },
  ],
});
