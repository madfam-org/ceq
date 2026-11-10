export type CeqBillingPlanId = "creator" | "pro_artist" | "studio";

export interface CeqBillingPlan {
  id: CeqBillingPlanId;
  name: string;
  priceLabel: string;
  creditLabel: string;
  tierSlug: string;
  checkoutEnabled: boolean;
  features: string[];
}

export const CEQ_BILLING_PRODUCT = "ceq";

export const CEQ_BILLING_PLANS: CeqBillingPlan[] = [
  {
    id: "creator",
    name: "Creator",
    priceLabel: "$0",
    creditLabel: "100 credits / month",
    tierSlug: "creator",
    checkoutEnabled: false,
    features: ["Landing/demo access", "Render API trial", "Community support"],
  },
  {
    id: "pro_artist",
    name: "Pro Artist",
    priceLabel: "MXN $349 / month",
    creditLabel: "2,000 credits / month",
    tierSlug: "pro_artist",
    checkoutEnabled: true,
    features: ["Studio access", "Private generations", "Priority queue tier"],
  },
  {
    id: "studio",
    name: "Studio",
    priceLabel: "MXN $1,299 / month",
    creditLabel: "10,000 credits / month",
    tierSlug: "studio",
    checkoutEnabled: true,
    features: ["Team workflows", "Shared credit pool", "Priority support"],
  },
];

export function isDhanamCheckoutEnabled(): boolean {
  return process.env.NEXT_PUBLIC_CEQ_CHECKOUT_ENABLED === "true";
}

/**
 * Dhanam's hosted checkout. A product links buyers here with
 * `?plan=<product>_<tier>&product=<product>&return_url=<absolute>`; the buyer
 * signs in with Janua on Dhanam's page, so identity never travels in the link.
 */
export const DHANAM_HOSTED_CHECKOUT_URL = "https://app.dhan.am/checkout";

const CHECKOUT_PATH = "/checkout";

/**
 * The hosted-checkout base: `NEXT_PUBLIC_DHANAM_CHECKOUT_URL` when it is an
 * absolute http(s) URL whose path is exactly `/checkout` (no query or
 * fragment), else {@link DHANAM_HOSTED_CHECKOUT_URL}. Anything else (the old
 * `api.dhan.am` billing base, a `/billing/checkout` path) is ignored, so a stale
 * variable can never resurrect the dead signed link.
 */
export function getDhanamCheckoutUrl(
  configured: string | undefined = process.env.NEXT_PUBLIC_DHANAM_CHECKOUT_URL,
): string {
  const value = configured?.trim();
  if (!value) return DHANAM_HOSTED_CHECKOUT_URL;

  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return DHANAM_HOSTED_CHECKOUT_URL;
  }

  const path = url.pathname.replace(/\/+$/, "");
  if (
    (url.protocol !== "https:" && url.protocol !== "http:") ||
    path !== CHECKOUT_PATH ||
    url.search ||
    url.hash ||
    url.username ||
    url.password
  ) {
    return DHANAM_HOSTED_CHECKOUT_URL;
  }

  return `${url.origin}${CHECKOUT_PATH}`;
}

export function getBillingPlan(id: CeqBillingPlanId): CeqBillingPlan {
  const plan = CEQ_BILLING_PLANS.find((item) => item.id === id);
  if (!plan) {
    throw new Error(`Unknown CEQ billing plan: ${id}`);
  }
  return plan;
}

/** Dhanam catalog plan id for a CEQ tier: `<product>_<tierSlug>`. */
export function dhanamPlanId(plan: CeqBillingPlan): string {
  return `${CEQ_BILLING_PRODUCT}_${plan.tierSlug}`;
}

/**
 * Link to Dhanam's hosted checkout for a sellable CEQ tier.
 *
 * Throws for a tier that is not sold (the free Creator tier) and for a
 * `returnUrl` that is not an absolute http(s) URL: Dhanam only returns buyers
 * to absolute https URLs on its allowlist.
 */
export function buildDhanamCheckoutUrl({
  planId,
  returnUrl,
  checkoutUrl = getDhanamCheckoutUrl(),
}: {
  planId: CeqBillingPlanId;
  returnUrl: string;
  checkoutUrl?: string;
}): string {
  const plan = getBillingPlan(planId);
  if (!plan.checkoutEnabled) {
    throw new Error(`Plan ${planId} does not support checkout.`);
  }

  let absoluteReturnUrl: URL;
  try {
    absoluteReturnUrl = new URL(returnUrl);
  } catch {
    throw new Error(`Checkout return URL must be absolute: ${returnUrl}`);
  }
  if (absoluteReturnUrl.protocol !== "https:" && absoluteReturnUrl.protocol !== "http:") {
    throw new Error(`Checkout return URL must be http(s): ${returnUrl}`);
  }

  const params = new URLSearchParams({
    plan: dhanamPlanId(plan),
    product: CEQ_BILLING_PRODUCT,
    return_url: absoluteReturnUrl.toString(),
  });

  return `${getDhanamCheckoutUrl(checkoutUrl)}?${params.toString()}`;
}
