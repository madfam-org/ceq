import type { Page } from "@playwright/test";
import { installStudioApiMocks } from "./api-mocks";

/**
 * Install browser-side API mocks for authenticated shell tests.
 *
 * Janua OIDC is mocked by `e2e/mock-janua-server.mjs` (see playwright.config.ts).
 * Studio API routes call Janua server-side, so browser route interception alone
 * cannot satisfy token exchange.
 */
export async function installAuthenticatedShellMocks(page: Page): Promise<void> {
  await installStudioApiMocks(page);
}
