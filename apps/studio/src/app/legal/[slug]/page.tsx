import Link from "next/link";
import { notFound } from "next/navigation";

import { Button } from "@/components/ui/button";

const UPDATED = "June 1, 2026";

const PAGES = {
  terms: {
    title: "CEQ Terms",
    sections: [
      {
        heading: "Service",
        body: "CEQ provides creative rendering, workflow orchestration, and generated asset storage for authenticated MADFAM users and approved customers.",
      },
      {
        heading: "Accounts",
        body: "Users authenticate through Janua. Account access, roles, and plan state may be suspended when abuse, payment failure, or policy violations are detected.",
      },
      {
        heading: "Billing",
        body: "Paid CEQ plans are billed through Dhanam. Credits, quotas, invoices, receipts, and plan changes are not final until Dhanam confirms the billing event.",
      },
      {
        heading: "Outputs",
        body: "Generated outputs remain subject to the prompt, source asset, model, and workflow constraints that produced them. Users are responsible for reviewing outputs before commercial use.",
      },
    ],
  },
  privacy: {
    title: "CEQ Privacy",
    sections: [
      {
        heading: "Data",
        body: "CEQ processes account identifiers, prompts, workflow parameters, generated assets, logs, and billing references needed to operate the service.",
      },
      {
        heading: "Processors",
        body: "CEQ uses MADFAM platform services including Janua for identity, Dhanam for billing, Cloudflare R2 for object storage, and Enclii for production operations.",
      },
      {
        heading: "Access",
        body: "Operational access is limited to authorized MADFAM staff and logged through platform controls where available.",
      },
    ],
  },
  "acceptable-use": {
    title: "CEQ Acceptable Use",
    sections: [
      {
        heading: "Allowed use",
        body: "Use CEQ for lawful creative, product, marketing, educational, and internal production workflows.",
      },
      {
        heading: "Disallowed use",
        body: "Do not use CEQ to generate illegal content, impersonation, non-consensual sexual content, instructions for harm, credential theft, malware, or abusive automated traffic.",
      },
      {
        heading: "Enforcement",
        body: "MADFAM may limit, suspend, or terminate access when CEQ usage creates legal, security, platform, or operational risk.",
      },
    ],
  },
  retention: {
    title: "Generated Media Retention",
    sections: [
      {
        heading: "Storage",
        body: "Generated assets may be stored in CEQ's R2-backed output and render cache buckets to support gallery access, deterministic URLs, and auditability.",
      },
      {
        heading: "Deletion",
        body: "Deletion and export workflows are handled by support until self-service retention controls are published.",
      },
      {
        heading: "Logs",
        body: "Operational logs may retain request IDs, job IDs, timestamps, status changes, and error metadata for reliability and incident review.",
      },
    ],
  },
  refunds: {
    title: "Refund and Support Terms",
    sections: [
      {
        heading: "Billing adjustments",
        body: "Billing adjustments, refunds, and credit grants are handled through Dhanam-backed records and CEQ credit ledger entries.",
      },
      {
        heading: "Failed jobs",
        body: "When a metered GPU job fails or is cancelled after a CEQ debit, CEQ records an idempotent refund entry when refund automation is enabled.",
      },
      {
        heading: "Support",
        body: "Support requests should include account email, job ID, request timestamp, and output URL when available.",
      },
    ],
  },
} as const;

type LegalSlug = keyof typeof PAGES;

export function generateStaticParams() {
  return Object.keys(PAGES).map((slug) => ({ slug }));
}

export default function LegalPage({ params }: { params: { slug: string } }) {
  const page = PAGES[params.slug as LegalSlug];
  if (!page) {
    notFound();
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-10">
        <header>
          <Link href="/" className="text-xl font-bold gradient-text">
            ceq
          </Link>
          <h1 className="mt-8 text-3xl font-bold">{page.title}</h1>
          <p className="mt-2 text-sm text-muted-foreground">Last updated: {UPDATED}</p>
        </header>

        <div className="space-y-6">
          {page.sections.map((section) => (
            <section key={section.heading}>
              <h2 className="text-lg font-semibold">{section.heading}</h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {section.body}
              </p>
            </section>
          ))}
        </div>

        <footer className="flex flex-wrap gap-2 border-t border-border pt-6">
          <Button asChild variant="outline" size="sm">
            <Link href="/billing">Billing</Link>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <Link href="/">Studio</Link>
          </Button>
        </footer>
      </div>
    </main>
  );
}
