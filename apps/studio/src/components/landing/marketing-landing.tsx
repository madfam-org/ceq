"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Check, Terminal, Zap, Layers, Workflow, Image as ImageIcon, Music2, Boxes, Lock, Bell, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/auth-context";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://api.ceq.lol";
const APP_BASE = process.env.NEXT_PUBLIC_APP_URL || "https://app.ceq.lol";

function isAppHost(): boolean {
  if (typeof window === "undefined") return false;
  const host = window.location.host;
  return host.startsWith("app.") || host === "localhost" || host.startsWith("localhost:");
}

function startSignIn(returnTo: string, login: (path: string) => void) {
  // On app.ceq.lol the existing useAuth().login() handles OIDC handoff.
  // On ceq.lol, we redirect users to app.ceq.lol where the OIDC redirect_uri
  // is registered with Janua.
  if (isAppHost()) {
    login(returnTo);
    return;
  }
  if (typeof window !== "undefined") {
    window.location.href = `${APP_BASE}${returnTo === "/" ? "" : returnTo}`;
  }
}

const PAIN_POINTS = [
  {
    title: "ComfyUI is a labyrinth.",
    body: "You spent the weekend wiring nodes instead of shipping. Every new model means re-learning the graph. Your team can't reproduce your renders.",
  },
  {
    title: "Midjourney + Discord scales like a hostage situation.",
    body: "No queue control. No team workspace. No determinism. Your client wants the SAME hero shot in 3 aspect ratios — good luck.",
  },
  {
    title: "Cloud GPU bills are a slot machine.",
    body: "RunDiffusion / RunPod / Vast.ai all bill differently. You can't tell whether one render cost 2 MXN or 200 MXN until the credit card statement lands.",
  },
  {
    title: "Your assets aren't versioned.",
    body: "Same prompt, six months later — different LoRA, different result. No content-addressed cache. Re-rendering the same shot wastes tokens you already paid for.",
  },
  {
    title: "Your pipeline isn't a pipeline.",
    body: "It's a Notion doc + a Figma + a Drive folder + a Slack thread. The asset that ships is whichever PNG someone DM'd last.",
  },
  {
    title: "You can't share renders without leaking workflows.",
    body: "PNG metadata exposes your prompts, seeds, models. Either you strip it (and lose the audit trail) or you ship trade secrets to clients.",
  },
];

const FEATURES = [
  {
    icon: Workflow,
    title: "Full ComfyUI graph, behind a clean UI.",
    body: "When you need to wire a custom KSampler, click 'Open Graph.' The other 95% of the time, ceq's templated UI gets you to a render in 4 clicks.",
  },
  {
    icon: Layers,
    title: "Templates as first-class citizens.",
    body: "Card thumbnails, social squares, video frames, 3D plates — content-addressed and R2-cached. Identical inputs always return the same URL. Already powering Rondelio's stratum-tcg cartridge.",
  },
  {
    icon: ImageIcon,
    title: "Deterministic /v1/render endpoints.",
    body: "Card, thumbnail, audio, 3D — call from any service via @ceq/sdk or HTTP. Hash-identical inputs hit cache; bills don't.",
  },
  {
    icon: Music2,
    title: "Multi-modal, not just images.",
    body: "Parametric audio (sine + ADSR) and 3D (glTF binary) ship today. Video clone workflows in Q3.",
  },
  {
    icon: Terminal,
    title: "Hacker-centric ergonomics.",
    body: "Dark mode only. Mono fonts. Command palette (⌘K). Real keyboard shortcuts. We built this for builders, not for managers reviewing campaigns from an iPad.",
  },
  {
    icon: Boxes,
    title: "Self-hostable. Single-tenant on request.",
    body: "Don't trust a hosted control plane with your pipeline? Deploy ceq on your own k3s. The asset pillar doesn't move.",
  },
];

const TIERS = [
  {
    name: "Creator",
    price: "$0",
    period: "/ month",
    blurb: "Get a feel for the studio without a card.",
    features: [
      "100 credits / month",
      "All public templates",
      "Community Discord",
      "Watermarked exports",
      "Public render gallery",
    ],
    cta: { label: "Start free", href: "/login", variant: "secondary" as const },
    highlight: false,
  },
  {
    name: "Pro Artist",
    price: "MXN $349",
    period: "/ month",
    blurb: "For the solo creator with deadlines.",
    features: [
      "2,000 credits / month",
      "All templates + workflow uploads",
      "Private gallery + R2 cache",
      "No watermark",
      "Email support, 24h response",
      "Webhook + SDK access",
    ],
    cta: { label: "Get notified at launch", interest: "ceq_pro_artist" },
    highlight: true,
  },
  {
    name: "Studio",
    price: "MXN $1,299",
    period: "/ month",
    blurb: "Teams shipping serial content for clients.",
    features: [
      "10,000 credits / month",
      "Team workspaces (5 seats)",
      "Brand kits + LoRA library",
      "Priority queue + dedicated GPU pool",
      "Slack/SOC support, 4h response",
      "Audit log + render attestation",
    ],
    cta: { label: "Talk to founders", interest: "ceq_studio" },
    highlight: false,
  },
];

const FAQS = [
  {
    q: "Why is this priced in MXN?",
    a: "MADFAM is a Mexico-first venture studio. Our infra is Hetzner + Cloudflare with MXN-denominated billing through our own platform (Dhanam). USD/EUR billing arrives when there's enough demand — meanwhile, MXN is what we charge in.",
  },
  {
    q: "Is ceq just a ComfyUI re-skin?",
    a: "No. ceq adds a deterministic, content-addressed asset pillar (/v1/render/* with R2 caching), template registries, multi-tenant queue control, audit logging, and the @ceq/sdk that other MADFAM products consume. The ComfyUI graph is one of several execution backends.",
  },
  {
    q: "Can I bring my own GPU?",
    a: "Yes. Studio tier supports BYO worker nodes — register your GPU host as a worker, ceq dispatches jobs to it. Useful for keeping training data on-prem.",
  },
  {
    q: "What happens to my prompts and outputs?",
    a: "Stored in your private bucket on R2 (or your S3 if BYO). Never used as training data. PNG metadata is stripped from public-gallery exports unless you opt in.",
  },
  {
    q: "When does Pro Artist actually launch?",
    a: "We're closing on 50 founding members before flipping the billing flag. The 'Get notified' button gets you on the launch list and locks in founding-member pricing for life.",
  },
  {
    q: "Do you have a refund policy?",
    a: "Cancel anytime; pro-rated refund within 7 days of the most recent charge if you've used <10% of your render quota. Beyond that, no refunds — we're a studio, not a metered utility.",
  },
];

export function MarketingLanding() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <NavBar />
      <Hero />
      <PainSection />
      <FeatureSection />
      <PricingSection />
      <FAQSection />
      <FinalCTA />
      <Footer />
    </div>
  );
}

function NavBar() {
  const { login } = useAuth();
  return (
    <nav className="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xl font-bold gradient-text">ceq</span>
          <Badge variant="outline" className="hidden md:inline-flex font-mono text-[10px]">
            v0.1.0 · entropy stable
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="#pricing"
            className="hidden sm:inline-block px-3 py-1.5 text-sm font-mono text-muted-foreground hover:text-foreground transition-colors"
          >
            Pricing
          </Link>
          <a
            href="https://github.com/madfam-org/ceq"
            target="_blank"
            rel="noopener noreferrer"
            className="hidden sm:inline-block px-3 py-1.5 text-sm font-mono text-muted-foreground hover:text-foreground transition-colors"
          >
            GitHub
          </a>
          <Button
            onClick={() => startSignIn("/", login)}
            variant="default"
            size="sm"
            className="font-mono"
          >
            Sign in
          </Button>
        </div>
      </div>
    </nav>
  );
}

function Hero() {
  const { login } = useAuth();
  return (
    <section className="relative overflow-hidden border-b border-border/50">
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-accent/10 pointer-events-none" />
      <div className="mx-auto max-w-6xl px-6 py-20 md:py-28">
        <div className="flex flex-col items-start gap-6 max-w-3xl">
          <Badge variant="outline" className="font-mono text-xs">
            <Zap className="mr-1.5 h-3 w-3 text-primary" />
            Render pipeline shipped 2026-04-19 · serving production traffic
          </Badge>
          <h1 className="text-4xl md:text-6xl font-bold leading-tight tracking-tight">
            Wrestle order from the chaos of{" "}
            <span className="gradient-text">latent space.</span>
          </h1>
          <p className="text-lg md:text-xl text-muted-foreground max-w-2xl leading-relaxed">
            ceq is the skunkworks terminal for the generative avant-garde. Full
            ComfyUI power when you need it, a clean UX when you don&apos;t. Deterministic
            renders, content-addressed cache, multi-modal templates — built by builders
            who got tired of wiring KSampler graphs at 2am.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 mt-2">
            <Button onClick={() => login("/")} size="lg" className="font-mono">
              Start rendering free
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
            <Link href="#pricing">
              <Button size="lg" variant="outline" className="font-mono w-full sm:w-auto">
                See pricing
              </Button>
            </Link>
          </div>
          <p className="text-xs font-mono text-muted-foreground mt-2">
            100 free credits/month, no credit card. Sign in with Janua (GitHub, Google, email).
          </p>
        </div>
      </div>
    </section>
  );
}

function PainSection() {
  return (
    <section className="border-b border-border/50 bg-card/30">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <div className="max-w-3xl mb-12">
          <p className="text-sm font-mono text-primary mb-3">› the bleeding-neck</p>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">
            If any of this rings true, you&apos;re in the right place.
          </h2>
          <p className="text-base text-muted-foreground">
            Generative AI tooling in 2026 is a graveyard of half-finished workflows.
            Here&apos;s what every solo creator and studio team we&apos;ve talked to says
            keeps them up.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {PAIN_POINTS.map((p) => (
            <Card key={p.title} className="bg-background/50 border-border/50">
              <CardContent className="p-5">
                <h3 className="font-mono text-sm font-semibold text-primary mb-2">
                  {p.title}
                </h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{p.body}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}

function FeatureSection() {
  return (
    <section className="border-b border-border/50">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <div className="max-w-3xl mb-12">
          <p className="text-sm font-mono text-primary mb-3">› what ceq actually does</p>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">
            One terminal. Every modality. Deterministic by default.
          </h2>
          <p className="text-base text-muted-foreground">
            We didn&apos;t build a Midjourney clone with extra steps. We built the
            pipeline that MADFAM&apos;s own products run on — Rondelio&apos;s
            stratum-tcg cartridge ships card art via ceq&apos;s @ceq/sdk in production
            today.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f) => {
            const Icon = f.icon;
            return (
              <Card key={f.title} className="bg-card/50 border-border/50 hover:border-primary/50 transition-colors">
                <CardContent className="p-5">
                  <Icon className="h-5 w-5 text-primary mb-3" />
                  <h3 className="font-semibold mb-2">{f.title}</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {f.body}
                  </p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function PricingSection() {
  return (
    <section id="pricing" className="border-b border-border/50 bg-card/30">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <div className="max-w-3xl mb-12">
          <p className="text-sm font-mono text-primary mb-3">› pricing</p>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">
            Three tiers. No usage-based slot machine.
          </h2>
          <p className="text-base text-muted-foreground">
            Monthly credit budgets that roll over up to 2× the tier cap. Cards burn
            ~5 credits, audio ~3, 3D ~10. Pricing reflects MX-first infrastructure
            costs — billed in MXN via Dhanam, our own platform-billing stack.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {TIERS.map((tier) => (
            <PricingCard key={tier.name} tier={tier} />
          ))}
        </div>
        <p className="mt-8 text-xs font-mono text-muted-foreground text-center">
          Founding-member pricing locks in for life. Tiers and limits may shift before
          paid billing flips on.
        </p>
      </div>
    </section>
  );
}

function PricingCard({ tier }: { tier: (typeof TIERS)[number] }) {
  return (
    <Card
      className={cn(
        "relative bg-background/50 border-border/50 flex flex-col",
        tier.highlight && "border-primary/60 shadow-lg shadow-primary/10",
      )}
    >
      {tier.highlight && (
        <Badge className="absolute -top-3 left-1/2 -translate-x-1/2 font-mono text-[10px]">
          Most popular
        </Badge>
      )}
      <CardContent className="flex flex-col flex-1 p-6 gap-4">
        <div>
          <h3 className="font-mono text-lg font-bold">{tier.name}</h3>
          <p className="text-sm text-muted-foreground mt-1">{tier.blurb}</p>
        </div>
        <div className="flex items-baseline gap-1">
          <span className="text-3xl font-bold tracking-tight">{tier.price}</span>
          <span className="text-sm text-muted-foreground">{tier.period}</span>
        </div>
        <ul className="flex flex-col gap-2 mt-2 flex-1">
          {tier.features.map((f) => (
            <li key={f} className="flex items-start gap-2 text-sm">
              <Check className="h-4 w-4 mt-0.5 text-primary shrink-0" />
              <span className="text-muted-foreground">{f}</span>
            </li>
          ))}
        </ul>
        <PricingCTA cta={tier.cta} highlight={tier.highlight} tierName={tier.name} />
      </CardContent>
    </Card>
  );
}

type CtaConfig =
  | { label: string; href: string; variant?: "default" | "secondary" | "outline" }
  | { label: string; interest: string };

function PricingCTA({
  cta,
  highlight,
  tierName,
}: {
  cta: CtaConfig;
  highlight: boolean;
  tierName: string;
}) {
  const { login } = useAuth();
  const [open, setOpen] = useState(false);

  if ("href" in cta) {
    return (
      <Button
        onClick={() => login(cta.href)}
        variant={highlight ? "default" : (cta.variant ?? "secondary")}
        className="w-full font-mono"
      >
        {cta.label}
      </Button>
    );
  }

  return (
    <>
      <Button
        onClick={() => setOpen(true)}
        variant={highlight ? "default" : "outline"}
        className="w-full font-mono"
      >
        <Bell className="mr-2 h-3.5 w-3.5" />
        {cta.label}
      </Button>
      {open && (
        <InterestCapture
          featureKey={cta.interest}
          tierName={tierName}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

function InterestCapture({
  featureKey,
  tierName,
  onClose,
}: {
  featureKey: string;
  tierName: string;
  onClose: () => void;
}) {
  const { user, isAuthenticated } = useAuth();
  const [email, setEmail] = useState(user?.email ?? "");
  const [note, setNote] = useState("");
  const [state, setState] = useState<"idle" | "loading" | "ok" | "err">("idle");
  const [errMsg, setErrMsg] = useState("");

  const submit = async () => {
    setState("loading");
    setErrMsg("");
    try {
      const res = await fetch(`${API_BASE}/v1/interest/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          feature_key: featureKey,
          email: email.trim(),
          note: note.trim() || undefined,
          source: "landing_pricing",
        }),
      });
      if (!res.ok && res.status !== 200 && res.status !== 201) {
        const body = await res.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      setState("ok");
    } catch (e) {
      setState("err");
      setErrMsg(e instanceof Error ? e.message : "Network error");
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <Card
        className="max-w-md w-full bg-card border-primary/40"
        onClick={(e) => e.stopPropagation()}
      >
        <CardContent className="p-6 flex flex-col gap-4">
          {state !== "ok" ? (
            <>
              <div>
                <h3 className="text-lg font-bold font-mono">
                  Get on the {tierName} list
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Founding-member pricing locks in for life. We&apos;ll email you when
                  billing flips on (and never spam you).
                </p>
              </div>
              <div className="flex flex-col gap-3">
                <Input
                  type="email"
                  placeholder="you@studio.tld"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={isAuthenticated}
                  className="font-mono"
                />
                <Textarea
                  placeholder="What would you use ceq for? (optional, but helps us prioritize)"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={3}
                  className="font-mono text-sm"
                />
                {state === "err" && (
                  <p className="text-xs text-destructive font-mono">{errMsg}</p>
                )}
                <div className="flex gap-2">
                  <Button
                    onClick={submit}
                    disabled={state === "loading" || !email.includes("@")}
                    className="flex-1 font-mono"
                  >
                    {state === "loading" ? (
                      <>
                        <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                        Sending
                      </>
                    ) : (
                      <>
                        <Bell className="mr-2 h-3.5 w-3.5" />
                        Notify me
                      </>
                    )}
                  </Button>
                  <Button onClick={onClose} variant="outline" className="font-mono">
                    Cancel
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center text-center py-4 gap-3">
              <div className="rounded-full bg-primary/10 p-3">
                <Check className="h-6 w-6 text-primary" />
              </div>
              <h3 className="text-lg font-bold font-mono">You&apos;re on the list.</h3>
              <p className="text-sm text-muted-foreground">
                We&apos;ll email <span className="font-mono text-foreground">{email}</span>{" "}
                when {tierName} launches. Founding-member pricing locked.
              </p>
              <Button onClick={onClose} className="mt-2 font-mono w-full">
                Close
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function FAQSection() {
  return (
    <section className="border-b border-border/50">
      <div className="mx-auto max-w-3xl px-6 py-20">
        <p className="text-sm font-mono text-primary mb-3">› the practical questions</p>
        <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-10">
          Things you&apos;d ask if we were in a bar.
        </h2>
        <div className="flex flex-col gap-4">
          {FAQS.map((f) => (
            <details
              key={f.q}
              className="group bg-card/50 border border-border/50 rounded-md p-5 hover:border-primary/50 transition-colors"
            >
              <summary className="cursor-pointer font-semibold flex items-center justify-between gap-4 list-none">
                <span>{f.q}</span>
                <span className="font-mono text-primary text-lg group-open:rotate-45 transition-transform">
                  +
                </span>
              </summary>
              <p className="mt-3 text-sm text-muted-foreground leading-relaxed">{f.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

function FinalCTA() {
  const { login } = useAuth();
  return (
    <section className="border-b border-border/50 bg-gradient-to-br from-primary/10 via-transparent to-accent/10">
      <div className="mx-auto max-w-3xl px-6 py-20 text-center flex flex-col items-center gap-5">
        <Lock className="h-8 w-8 text-primary" />
        <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
          Stop losing weekends to broken pipelines.
        </h2>
        <p className="text-base text-muted-foreground max-w-xl">
          100 free credits a month. Sign in with Janua. If ceq doesn&apos;t replace at
          least one tool in your stack within 30 minutes, you owe us nothing.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 mt-2">
          <Button onClick={() => login("/")} size="lg" className="font-mono">
            Start free <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
          <Link href="#pricing">
            <Button size="lg" variant="outline" className="font-mono w-full sm:w-auto">
              See pricing first
            </Button>
          </Link>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="bg-background">
      <div className="mx-auto max-w-6xl px-6 py-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <span className="font-mono text-sm font-bold gradient-text">ceq</span>
          <span className="text-xs text-muted-foreground font-mono">
            Signal acquired. © {new Date().getFullYear()}{" "}
            <a
              href="https://madfam.io"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-foreground transition-colors"
            >
              Innovaciones MADFAM
            </a>
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs font-mono text-muted-foreground">
          <a
            href="https://github.com/madfam-org/ceq"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-foreground transition-colors"
          >
            GitHub
          </a>
          <a
            href="https://api.ceq.lol/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-foreground transition-colors"
          >
            API docs
          </a>
          <Link href="/templates" className="hover:text-foreground transition-colors">
            Templates
          </Link>
          <a
            href="https://status.madfam.io"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-foreground transition-colors"
          >
            Status
          </a>
        </div>
      </div>
    </footer>
  );
}
