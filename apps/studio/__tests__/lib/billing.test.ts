import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildDhanamCheckoutUrl,
  CEQ_BILLING_PLANS,
  DHANAM_HOSTED_CHECKOUT_URL,
  dhanamPlanId,
  getDhanamCheckoutUrl,
  isDhanamCheckoutEnabled,
  type CeqBillingPlanId,
} from "@/lib/billing";

const RETURN_URL = "https://app.ceq.lol/billing";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("Dhanam hosted checkout links", () => {
  // The exact link per sellable tier. Plan ids must match Dhanam's catalog
  // (`GET https://api.dhan.am/v1/billing/catalog`, product `ceq`).
  it.each<[CeqBillingPlanId, string]>([
    [
      "pro_artist",
      "https://app.dhan.am/checkout?plan=ceq_pro_artist&product=ceq&return_url=https%3A%2F%2Fapp.ceq.lol%2Fbilling",
    ],
    [
      "studio",
      "https://app.dhan.am/checkout?plan=ceq_studio&product=ceq&return_url=https%3A%2F%2Fapp.ceq.lol%2Fbilling",
    ],
  ])("builds the exact hosted-checkout link for %s", (planId, expected) => {
    expect(buildDhanamCheckoutUrl({ planId, returnUrl: RETURN_URL })).toBe(expected);
  });

  it("never emits the retired signed link or an identity", () => {
    for (const plan of CEQ_BILLING_PLANS.filter((item) => item.checkoutEnabled)) {
      const url = buildDhanamCheckoutUrl({ planId: plan.id, returnUrl: RETURN_URL });
      expect(url).not.toContain("api.dhan.am");
      expect(url).not.toContain("/billing/checkout");
      expect(url).not.toContain("user_id");
      expect(url.startsWith(`${DHANAM_HOSTED_CHECKOUT_URL}?`)).toBe(true);
    }
  });

  it("names every sellable tier as <product>_<tierSlug>", () => {
    const sellable = CEQ_BILLING_PLANS.filter((plan) => plan.checkoutEnabled).map(dhanamPlanId);
    expect(sellable).toEqual(["ceq_pro_artist", "ceq_studio"]);
  });

  it("rejects checkout for the free creator tier", () => {
    expect(() =>
      buildDhanamCheckoutUrl({ planId: "creator", returnUrl: RETURN_URL }),
    ).toThrow("does not support checkout");
  });

  it("rejects an unknown tier", () => {
    expect(() =>
      buildDhanamCheckoutUrl({
        planId: "enterprise" as CeqBillingPlanId,
        returnUrl: RETURN_URL,
      }),
    ).toThrow("Unknown CEQ billing plan");
  });

  it("requires an absolute http(s) return URL", () => {
    expect(() =>
      buildDhanamCheckoutUrl({ planId: "studio", returnUrl: "/billing" }),
    ).toThrow("must be absolute");
    expect(() =>
      buildDhanamCheckoutUrl({ planId: "studio", returnUrl: "javascript:alert(1)" }),
    ).toThrow("must be http(s)");
  });

  it("uses a configured hosted-checkout base", () => {
    expect(
      buildDhanamCheckoutUrl({
        planId: "pro_artist",
        returnUrl: RETURN_URL,
        checkoutUrl: "https://staging.dhan.am/checkout/",
      }),
    ).toBe(
      "https://staging.dhan.am/checkout?plan=ceq_pro_artist&product=ceq&return_url=https%3A%2F%2Fapp.ceq.lol%2Fbilling",
    );
  });
});

describe("hosted-checkout base", () => {
  it("defaults to app.dhan.am/checkout when unset or blank", () => {
    vi.stubEnv("NEXT_PUBLIC_DHANAM_CHECKOUT_URL", "");
    expect(getDhanamCheckoutUrl()).toBe("https://app.dhan.am/checkout");
    expect(getDhanamCheckoutUrl(undefined)).toBe("https://app.dhan.am/checkout");
    expect(getDhanamCheckoutUrl("   ")).toBe("https://app.dhan.am/checkout");
  });

  it("reads NEXT_PUBLIC_DHANAM_CHECKOUT_URL", () => {
    vi.stubEnv("NEXT_PUBLIC_DHANAM_CHECKOUT_URL", "https://staging.dhan.am/checkout");
    expect(getDhanamCheckoutUrl()).toBe("https://staging.dhan.am/checkout");
  });

  it.each([
    ["the retired API billing base", "https://api.dhan.am"],
    ["the retired signed-link path", "https://api.dhan.am/billing/checkout"],
    ["a path other than /checkout", "https://app.dhan.am/billing"],
    ["a base with a query", "https://app.dhan.am/checkout?plan=x"],
    ["a base with credentials", "https://user:pass@app.dhan.am/checkout"],
    ["a relative path", "/checkout"],
    ["a non-http scheme", "ftp://app.dhan.am/checkout"],
  ])("ignores %s", (_label, configured) => {
    expect(getDhanamCheckoutUrl(configured)).toBe(DHANAM_HOSTED_CHECKOUT_URL);
  });
});

describe("checkout switch", () => {
  it("is on only for the exact string true", () => {
    vi.stubEnv("NEXT_PUBLIC_CEQ_CHECKOUT_ENABLED", "true");
    expect(isDhanamCheckoutEnabled()).toBe(true);

    vi.stubEnv("NEXT_PUBLIC_CEQ_CHECKOUT_ENABLED", "TRUE");
    expect(isDhanamCheckoutEnabled()).toBe(false);

    vi.stubEnv("NEXT_PUBLIC_CEQ_CHECKOUT_ENABLED", "");
    expect(isDhanamCheckoutEnabled()).toBe(false);
  });
});
