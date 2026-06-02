import { describe, expect, it, vi } from "vitest";

import {
  buildDhanamCheckoutUrl,
  getDhanamBillingBaseUrl,
  isDhanamCheckoutEnabled,
} from "@/lib/billing";

describe("billing helpers", () => {
  it("builds Dhanam checkout URLs with CEQ product context", () => {
    const url = buildDhanamCheckoutUrl({
      baseUrl: "https://api.dhan.am/",
      planId: "pro_artist",
      userId: "user-123",
      returnUrl: "https://app.ceq.lol/billing",
    });

    expect(url).toBe(
      "https://api.dhan.am/billing/checkout?plan=pro_artist&product=ceq&user_id=user-123&return_url=https%3A%2F%2Fapp.ceq.lol%2Fbilling",
    );
  });

  it("rejects checkout for the free creator plan", () => {
    expect(() =>
      buildDhanamCheckoutUrl({
        planId: "creator",
        userId: "user-123",
        returnUrl: "https://app.ceq.lol/billing",
      }),
    ).toThrow("does not support checkout");
  });

  it("reads checkout config from public environment", () => {
    vi.stubEnv("NEXT_PUBLIC_CEQ_CHECKOUT_ENABLED", "true");
    vi.stubEnv("NEXT_PUBLIC_DHANAM_BILLING_URL", "https://billing.example.com/");

    expect(isDhanamCheckoutEnabled()).toBe(true);
    expect(getDhanamBillingBaseUrl()).toBe("https://billing.example.com");

    vi.unstubAllEnvs();
  });
});
