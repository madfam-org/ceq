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

export function getDhanamBillingBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_DHANAM_BILLING_URL || "https://api.dhan.am").replace(
    /\/+$/,
    "",
  );
}

export function getBillingPlan(id: CeqBillingPlanId): CeqBillingPlan {
  const plan = CEQ_BILLING_PLANS.find((item) => item.id === id);
  if (!plan) {
    throw new Error(`Unknown CEQ billing plan: ${id}`);
  }
  return plan;
}

export function buildDhanamCheckoutUrl({
  planId,
  userId,
  returnUrl,
  baseUrl = getDhanamBillingBaseUrl(),
}: {
  planId: CeqBillingPlanId;
  userId: string;
  returnUrl: string;
  baseUrl?: string;
}): string {
  const plan = getBillingPlan(planId);
  if (!plan.checkoutEnabled) {
    throw new Error(`Plan ${planId} does not support checkout.`);
  }

  const params = new URLSearchParams({
    plan: plan.tierSlug,
    product: CEQ_BILLING_PRODUCT,
    user_id: userId,
    return_url: returnUrl,
  });

  return `${baseUrl.replace(/\/+$/, "")}/billing/checkout?${params.toString()}`;
}
