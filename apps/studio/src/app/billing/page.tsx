"use client";

import Link from "next/link";
import { CreditCard, ExternalLink, FileText, ShieldCheck } from "lucide-react";

import { MainLayout } from "@/components/layout/main-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/auth-context";
import {
  buildDhanamCheckoutUrl,
  CEQ_BILLING_PLANS,
  isDhanamCheckoutEnabled,
  type CeqBillingPlan,
} from "@/lib/billing";
import { useCreditBalance } from "@/lib/hooks";

const LEGAL_LINKS = [
  { href: "/legal/terms", label: "Terms" },
  { href: "/legal/privacy", label: "Privacy" },
  { href: "/legal/acceptable-use", label: "Acceptable use" },
  { href: "/legal/retention", label: "Retention" },
  { href: "/legal/refunds", label: "Refunds" },
];

function checkoutUrlFor(plan: CeqBillingPlan, userId: string): string | null {
  if (!plan.checkoutEnabled || !userId || !isDhanamCheckoutEnabled()) {
    return null;
  }

  const origin =
    typeof window === "undefined" ? "https://app.ceq.lol" : window.location.origin;

  return buildDhanamCheckoutUrl({
    planId: plan.id,
    userId,
    returnUrl: `${origin}/billing`,
  });
}

export default function BillingPage() {
  const { user } = useAuth();
  const balance = useCreditBalance(Boolean(user));
  const checkoutEnabled = isDhanamCheckoutEnabled();

  return (
    <MainLayout>
      <div className="flex flex-col gap-6 p-6">
        <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <CreditCard className="h-6 w-6 text-primary" />
              <h1 className="text-2xl font-bold">Billing</h1>
            </div>
            <p className="text-sm text-muted-foreground terminal-text">
              Dhanam-backed plans and CEQ credit balance
            </p>
          </div>
          <div className="ceq-card px-4 py-3 md:min-w-56">
            <p className="text-xs uppercase text-muted-foreground">Credits</p>
            <p className="mt-1 text-2xl font-semibold">
              {balance.data ? balance.data.balance.toLocaleString() : "--"}
            </p>
            <p className="text-xs text-muted-foreground">
              {balance.isError ? "Balance unavailable" : "Current account balance"}
            </p>
          </div>
        </header>

        <section className="grid gap-4 lg:grid-cols-3">
          {CEQ_BILLING_PLANS.map((plan) => {
            const checkoutUrl = checkoutUrlFor(plan, user?.id ?? "");
            return (
              <article key={plan.id} className="ceq-card flex min-h-80 flex-col p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold">{plan.name}</h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {plan.creditLabel}
                    </p>
                  </div>
                  {plan.checkoutEnabled ? (
                    <Badge variant="outline">Dhanam</Badge>
                  ) : (
                    <Badge variant="secondary">Included</Badge>
                  )}
                </div>

                <p className="mt-6 text-2xl font-bold">{plan.priceLabel}</p>

                <ul className="mt-5 space-y-2 text-sm text-muted-foreground">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex gap-2">
                      <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>

                <div className="mt-auto pt-6">
                  {checkoutUrl ? (
                    <Button asChild className="w-full">
                      <a href={checkoutUrl}>
                        <CreditCard className="h-4 w-4" />
                        Checkout
                      </a>
                    </Button>
                  ) : plan.checkoutEnabled ? (
                    <Button className="w-full" disabled>
                      <CreditCard className="h-4 w-4" />
                      {checkoutEnabled ? "Session required" : "Checkout pending"}
                    </Button>
                  ) : (
                    <Button asChild variant="outline" className="w-full">
                      <Link href="/templates">
                        <ExternalLink className="h-4 w-4" />
                        Open Studio
                      </Link>
                    </Button>
                  )}
                </div>
              </article>
            );
          })}
        </section>

        <section className="ceq-card p-5">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold">Commercial Docs</h2>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {LEGAL_LINKS.map((link) => (
              <Button key={link.href} asChild variant="outline" size="sm">
                <Link href={link.href}>{link.label}</Link>
              </Button>
            ))}
          </div>
        </section>
      </div>
    </MainLayout>
  );
}
