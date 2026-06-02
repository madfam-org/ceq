"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowRight,
  BadgeCheck,
  Bell,
  Boxes,
  Check,
  Code2,
  Copy,
  Database,
  ExternalLink,
  FileText,
  Gauge,
  Image as ImageIcon,
  KeyRound,
  Layers,
  Loader2,
  Lock,
  Music2,
  RefreshCcw,
  Repeat2,
  ShieldCheck,
  Sparkles,
  Terminal,
  Workflow,
  Zap,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/auth-context";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://api.ceq.lol";
const APP_BASE = process.env.NEXT_PUBLIC_APP_URL || "https://app.ceq.lol";

type LandingEventProperties = Record<string, boolean | number | string>;

interface DataLayerWindow extends Window {
  dataLayer?: Array<Record<string, unknown>>;
}

function trackLandingEvent(
  event: string,
  properties: LandingEventProperties = {},
): void {
  if (typeof window === "undefined") return;

  const detail = {
    event,
    properties,
    timestamp: new Date().toISOString(),
  };

  window.dispatchEvent(new CustomEvent("ceq:landing-event", { detail }));
  (window as DataLayerWindow).dataLayer?.push({
    event: `ceq_${event}`,
    ...properties,
  });
}

function isAppHost(): boolean {
  if (typeof window === "undefined") return false;
  const host = window.location.host;
  return host.startsWith("app.") || host === "localhost" || host.startsWith("localhost:");
}

function startSignIn(returnTo: string, login: (path: string) => void) {
  // On app.ceq.lol the existing useAuth().login() handles OIDC handoff.
  // On ceq.lol, redirect to app.ceq.lol where the Janua redirect_uri is registered.
  if (isAppHost()) {
    login(returnTo);
    return;
  }
  if (typeof window !== "undefined") {
    const url = new URL("/login", APP_BASE);
    url.searchParams.set("returnTo", returnTo);
    window.location.href = url.toString();
  }
}

const PROOF_POINTS = [
  { label: "100 free credits", detail: "no card required", icon: Sparkles },
  { label: "Deterministic URLs", detail: "same inputs, same asset", icon: Repeat2 },
  { label: "R2-backed cache", detail: "cache hits do not rebill", icon: Database },
  { label: "Studio + SDK", detail: "UI for humans, API for products", icon: Code2 },
];

const SUPERPOWERS = [
  {
    icon: Workflow,
    pain: "ComfyUI graphs break, drift, and scare teammates.",
    power: "Wrap graph complexity in reusable templates.",
    outcome: "Render in 4 clicks, then open the graph only when you need it.",
  },
  {
    icon: Repeat2,
    pain: "Clients ask for the exact same asset six weeks later.",
    power: "Content-addressed deterministic outputs.",
    outcome: "Reproduce instead of reinventing the shot from memory.",
  },
  {
    icon: Gauge,
    pain: "Cloud GPU cost is unknowable until the bill lands.",
    power: "Credits, visible render costs, and cache hits.",
    outcome: "Budget a batch before your team starts generating.",
  },
  {
    icon: Database,
    pain: "The final asset lives in Slack, Drive, Figma, and someone's Downloads.",
    power: "Private gallery, stable URLs, and R2-backed storage.",
    outcome: "One source of truth for every generated deliverable.",
  },
  {
    icon: KeyRound,
    pain: "Sharing outputs can leak prompts, seeds, models, and workflow IP.",
    power: "Client-facing exports with clean metadata boundaries.",
    outcome: "Share the asset without handing over the production recipe.",
  },
  {
    icon: Code2,
    pain: "Your product needs assets on demand, not another manual UI task.",
    power: "Render endpoints, webhooks, and @ceq/sdk.",
    outcome: "Automate generative assets inside real applications.",
  },
];

const ENGINE_FEATURES = [
  {
    icon: Workflow,
    title: "Full ComfyUI graph when needed.",
    body: "The clean Studio path handles the common run. The graph remains available for custom KSampler work and deeper pipeline surgery.",
  },
  {
    icon: Layers,
    title: "Templates are production objects.",
    body: "Card thumbnails, social squares, video frames, audio, and 3D plates move through a registry instead of loose prompt notes.",
  },
  {
    icon: ImageIcon,
    title: "Deterministic /v1/render endpoints.",
    body: "Card, thumbnail, audio, and 3D endpoints can be called by HTTP or @ceq/sdk. Hash-identical inputs resolve to the same cached output.",
  },
  {
    icon: Music2,
    title: "Multi-modal by design.",
    body: "Image, parametric audio, and glTF outputs ship today. Video workflows fit the same template and queue model as they come online.",
  },
  {
    icon: Terminal,
    title: "Built for operators.",
    body: "Dark terminal ergonomics, keyboard-first flows, command palette, and API access keep production users moving quickly.",
  },
  {
    icon: Boxes,
    title: "Hosted or single-tenant.",
    body: "Use CEQ hosted for speed, or run a dedicated deployment with your own worker nodes when data gravity requires it.",
  },
];

const DEMO_TEMPLATES = [
  {
    id: "card",
    apiPath: "card",
    label: "Card",
    title: "Card Standard",
    input: "Stratum Chronicle, obsidian palette, seed 91724",
    cost: "5 credits",
    url: "r2://ceq-assets/render/card-standard/b9f3.png",
    outputTitle: "STRATUM CHRONICLE",
    outputDetail: "512x768 PNG",
  },
  {
    id: "thumbnail",
    apiPath: "thumbnail",
    label: "Thumbnail",
    title: "Social Thumbnail",
    input: "Launch post, copper accent, 16:9 crop",
    cost: "4 credits",
    url: "r2://ceq-assets/render/thumbnail/f2a1.png",
    outputTitle: "FOUNDER DROP",
    outputDetail: "1280x720 PNG",
  },
  {
    id: "audio",
    apiPath: "audio",
    label: "Audio",
    title: "Tone Beep",
    input: "A4 pulse, 220ms attack, 0.6 gain",
    cost: "3 credits",
    url: "r2://ceq-assets/render/tone-beep/4c18.wav",
    outputTitle: "A4 SIGNAL",
    outputDetail: "22.05kHz WAV",
  },
  {
    id: "plate",
    apiPath: "3d",
    label: "3D Plate",
    title: "Card Plate",
    input: "Rounded plate, 12mm depth, matte black",
    cost: "10 credits",
    url: "r2://ceq-assets/render/card-plate/7e02.glb",
    outputTitle: "CARD PLATE",
    outputDetail: "glTF 2.0 binary",
  },
] as const;

type DemoTemplate = (typeof DEMO_TEMPLATES)[number];
type DemoTemplateId = DemoTemplate["id"];

const TIERS = [
  {
    name: "Creator",
    price: "$0",
    period: "/ month",
    blurb: "Validate your first repeatable workflow without a card.",
    credits: "100 credits",
    volume: "about 20 card renders",
    features: [
      "100 credits / month",
      "Public templates",
      "Watermarked exports",
      "Public render gallery",
    ],
    pill: "Start free now",
    cta: { label: "Start generating free", href: "/", variant: "secondary" as const },
    highlight: false,
  },
  {
    name: "Pro Artist",
    price: "MXN $349",
    period: "/ month",
    blurb: "For solo creators shipping paid work on deadlines.",
    credits: "2,000 credits",
    volume: "about 400 card renders",
    features: [
      "All templates + workflow uploads",
      "Private gallery + R2 cache",
      "No watermark",
      "Webhook + SDK access",
      "Email support, 24h response",
    ],
    cta: { label: "Reserve founder price", interest: "ceq_pro_artist" },
    pill: "Founding windows are limited",
    highlight: true,
  },
  {
    name: "Studio",
    price: "MXN $1,299",
    period: "/ month",
    blurb: "For teams generating repeatable assets for clients.",
    credits: "10,000 credits",
    volume: "about 2,000 card renders",
    features: [
      "Team workspaces (5 seats)",
      "Brand kits + LoRA library",
      "Priority queue + dedicated GPU pool",
      "Slack/SOC support, 4h response",
      "Audit log + render attestation",
    ],
    cta: { label: "Book studio pilot", interest: "ceq_studio" },
    pill: "Founding seats capped per quarter",
    highlight: false,
  },
];

const TRUST_ITEMS = [
  {
    icon: Lock,
    title: "Private outputs by default",
    body: "Studio and paid workflows keep generated assets in private storage instead of public Discord-style channels.",
  },
  {
    icon: ShieldCheck,
    title: "No training on customer prompts",
    body: "CEQ treats prompts, model choices, source assets, and generated outputs as customer production data.",
  },
  {
    icon: KeyRound,
    title: "Client-safe export boundaries",
    body: "Public sharing paths are designed to avoid leaking seeds, prompts, model names, and graph internals.",
  },
  {
    icon: FileText,
    title: "Commercial docs are linked",
    body: "Terms, privacy, acceptable use, retention, and refund surfaces are available before paid onboarding.",
  },
];

const FAQS = [
  {
    q: "Is CEQ just a ComfyUI re-skin?",
    a: "No. CEQ adds deterministic render endpoints, content-addressed caching, template registries, queue control, audit-oriented galleries, and the @ceq/sdk. ComfyUI is one execution backend, not the product boundary.",
  },
  {
    q: "Who should use CEQ first?",
    a: "Creators, agencies, and product teams that already feel the pain of repeating prompts, preserving seeds, controlling GPU cost, and delivering assets to clients or apps. If you only need one-off images, a consumer image generator may be enough.",
  },
  {
    q: "Can I bring my own GPU?",
    a: "Yes. Studio-tier deployments can support registered worker nodes when you need dedicated capacity or stronger data boundaries.",
  },
  {
    q: "What ROI should I expect in week one?",
    a: "Most teams replace their first repetitive asset job within 60 minutes if they have one stable prompt/template pattern. You usually win on consistency first, then spend predictability, then speed.",
  },
  {
    q: "Why is pricing in MXN?",
    a: "MADFAM is Mexico-first and Dhanam-backed billing is MXN-native. USD/EUR billing can follow demand; founding pricing is intentionally anchored to our current operating base.",
  },
  {
    q: "When does paid checkout turn on?",
    a: "Founding plans are being onboarded manually while Dhanam checkout and entitlement proof are finalized. Reserving a plan captures buying intent and locks founding-member pricing.",
  },
  {
    q: "What happens if a render fails?",
    a: "CEQ is built around job IDs, callbacks, output records, and credit ledger entries. Failed metered jobs can be reconciled through the credit/refund path as billing automation comes online.",
  },
];

export function MarketingLanding() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <NavBar />
      <Hero />
      <ProofStrip />
      <SuperpowerMatrix />
      <LandingDemo />
      <EngineSection />
      <PricingSection />
      <TrustSection />
      <FAQSection />
      <FinalCTA />
      <Footer />
    </div>
  );
}

function NavBar() {
  const { login } = useAuth();
  return (
    <nav className="sticky top-0 z-50 border-b border-border/50 bg-background/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xl font-bold gradient-text">ceq</span>
          <Badge variant="outline" className="hidden md:inline-flex font-mono text-[10px]">
            production assets, repeatable by default
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="#demo"
            className="hidden sm:inline-block px-3 py-1.5 text-sm font-mono text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => trackLandingEvent("nav_demo_click")}
          >
            Demo
          </Link>
          <Link
            href="#pricing"
            className="hidden sm:inline-block px-3 py-1.5 text-sm font-mono text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => trackLandingEvent("nav_pricing_click")}
          >
            Pricing
          </Link>
          <Button
            onClick={() => {
              trackLandingEvent("nav_sign_in_click");
              startSignIn("/", login);
            }}
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
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,hsl(var(--primary)/0.13),transparent_28%),radial-gradient(circle_at_85%_15%,hsl(var(--accent)/0.14),transparent_32%)] pointer-events-none" />
      <div className="relative mx-auto grid max-w-6xl gap-10 px-6 py-16 md:py-24 lg:grid-cols-[1fr_0.88fr] lg:items-center">
        <div className="flex max-w-3xl flex-col items-start gap-6">
          <Badge variant="outline" className="font-mono text-xs">
            <Zap className="mr-1.5 h-3 w-3 text-primary" />
            client-safe generative production
          </Badge>
          <div className="space-y-5">
            <h1 className="text-4xl font-bold leading-tight tracking-tight md:text-6xl">
              Generate repeatable client-ready AI assets without rebuilding{" "}
              <span className="gradient-text">ComfyUI graphs.</span>
            </h1>
            <p className="max-w-2xl text-lg leading-relaxed text-muted-foreground md:text-xl">
              CEQ turns prompts, models, templates, and GPU execution into
              versioned production workflows. Build once, run everywhere, and ship
              to clients with predictable costs and stable assets.
            </p>
          </div>
          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
            <Button
              onClick={() => {
                trackLandingEvent("hero_start_free_click");
                startSignIn("/", login);
              }}
              size="lg"
              className="font-mono"
            >
              Start generating free
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
            <Link
              href="#pricing"
              onClick={() => trackLandingEvent("hero_pilot_click")}
              className="sm:w-auto"
            >
              <Button size="lg" variant="outline" className="w-full font-mono sm:w-auto">
                Reserve founding access
              </Button>
            </Link>
          </div>
          <p className="max-w-2xl text-xs font-mono leading-5 text-muted-foreground">
            100 free credits/month. No credit card. Sign in with Janua, then convert
            your first recurring workflow inside a production-grade loop.
          </p>
        </div>

        <HeroProofPanel />
      </div>
    </section>
  );
}

function HeroProofPanel() {
  return (
    <div
      className="overflow-hidden rounded-lg border border-primary/30 bg-card/80 shadow-2xl shadow-primary/10"
      aria-label="CEQ deterministic render proof"
    >
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-primary" />
          <span className="font-mono text-sm font-semibold">ceq.render</span>
        </div>
        <Badge variant="outline" className="font-mono text-[10px]">
          cache hit
        </Badge>
      </div>

      <div className="grid gap-0 md:grid-cols-[0.9fr_1.1fr]">
        <div className="min-w-0 border-b border-border/60 p-4 md:border-b-0 md:border-r">
          <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
            Template
          </p>
          <h2 className="mt-2 text-lg font-semibold">card-standard</h2>
          <div className="mt-4 space-y-3 text-sm">
            <ProofField label="title" value="Stratum Chronicle" />
            <ProofField label="palette" value="obsidian / copper" />
            <ProofField label="seed" value="91724" />
          </div>
          <div className="mt-5 rounded-md border border-border/60 bg-background/70 p-3">
            <p className="mb-2 text-xs text-muted-foreground">SDK call</p>
            <pre className="overflow-hidden text-xs leading-5 text-foreground">
              {`await ceq.renderCard({
  template: "card-standard",
  seed: 91724
})`}
            </pre>
          </div>
        </div>

        <div className="min-w-0 p-4">
          <div className="mx-auto flex max-w-[260px] flex-col overflow-hidden rounded-lg border border-border/70 bg-background">
            <div className="aspect-[2/3] bg-[linear-gradient(145deg,#111827,#1f2937_45%,#7c2d12)] p-4">
              <div className="flex h-full flex-col justify-between rounded-md border border-primary/40 bg-black/25 p-4">
                <div>
                  <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-primary">
                    CEQ output
                  </p>
                  <h3 className="mt-3 text-xl font-bold leading-tight">
                    STRATUM CHRONICLE
                  </h3>
                </div>
                <div className="space-y-2">
                  <div className="h-2 w-3/4 rounded-full bg-primary/70" />
                  <div className="h-2 w-1/2 rounded-full bg-foreground/40" />
                  <div className="h-16 rounded-md border border-foreground/15 bg-foreground/10" />
                </div>
              </div>
            </div>
            <div className="space-y-2 border-t border-border/70 p-3">
              <ProofMetric label="cost" value="5 credits" />
              <ProofMetric label="url" value="render/card-standard/b9f3.png" />
              <ProofMetric label="rerun" value="same asset, no rebill" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProofField({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3 rounded-md border border-border/50 bg-background/50 px-3 py-2">
      <span className="font-mono text-xs text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-right font-mono text-xs">{value}</span>
    </div>
  );
}

function ProofMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3 text-xs">
      <span className="font-mono text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-right font-mono text-foreground">{value}</span>
    </div>
  );
}

function ProofStrip() {
  return (
    <section className="border-b border-border/50 bg-card/25">
      <div className="mx-auto grid max-w-6xl gap-3 px-6 py-6 md:grid-cols-4">
        {PROOF_POINTS.map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.label}
              className="flex items-center gap-3 rounded-md border border-border/50 bg-background/45 px-4 py-3"
            >
              <Icon className="h-5 w-5 shrink-0 text-primary" />
              <div>
                <p className="text-sm font-semibold">{item.label}</p>
                <p className="text-xs text-muted-foreground">{item.detail}</p>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function SuperpowerMatrix() {
  return (
    <section className="border-b border-border/50">
      <div className="mx-auto max-w-6xl px-6 py-16 md:py-20">
        <div className="mb-10 max-w-3xl">
          <p className="mb-3 text-sm font-mono text-primary">› what users unlock</p>
          <h2 className="mb-4 text-3xl font-bold tracking-tight md:text-4xl">
            CEQ gives your team production superpowers, not another prompt box.
          </h2>
          <p className="text-base leading-7 text-muted-foreground">
            The pain is not that generative AI cannot make images. The pain is making
            the same useful asset again, safely, at a known cost, for a real client or
            a revenue-facing workflow.
          </p>
        </div>

        <div className="overflow-hidden rounded-lg border border-border/60">
          <div className="hidden grid-cols-[1fr_1fr_0.9fr] border-b border-border/60 bg-card/50 px-4 py-3 text-xs font-mono uppercase tracking-[0.16em] text-muted-foreground md:grid">
            <span>Pain</span>
            <span>CEQ superpower</span>
            <span>Business outcome</span>
          </div>
          {SUPERPOWERS.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.pain}
                className="grid gap-4 border-b border-border/50 bg-background/35 p-4 last:border-b-0 md:grid-cols-[1fr_1fr_0.9fr] md:items-start"
              >
                <div className="flex gap-3">
                  <Icon className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                  <p className="text-sm text-muted-foreground">{item.pain}</p>
                </div>
                <p className="text-sm font-semibold">{item.power}</p>
                <p className="text-sm text-muted-foreground">{item.outcome}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function LandingDemo() {
  const [selectedId, setSelectedId] = useState<DemoTemplateId>("card");
  const [runCount, setRunCount] = useState(0);
  const selected =
    DEMO_TEMPLATES.find((template) => template.id === selectedId) ?? DEMO_TEMPLATES[0];
  const cacheHit = runCount > 0;

  return (
    <section id="demo" className="border-b border-border/50 bg-card/25">
      <div className="mx-auto max-w-6xl px-6 py-16 md:py-20">
        <div className="mb-10 max-w-3xl">
          <p className="mb-3 text-sm font-mono text-primary">› try the production loop</p>
          <h2 className="mb-4 text-3xl font-bold tracking-tight md:text-4xl">
            Template, render, reuse. The boring parts become automatic.
          </h2>
          <p className="text-base leading-7 text-muted-foreground">
            This demo is simulated for the landing page, but it mirrors the CEQ
            contract: choose a template, provide structured inputs, get a stable
            output URL and visible credit cost, then rerun identical inputs as a
            cache hit.
          </p>
        </div>

        <div className="overflow-hidden rounded-lg border border-primary/25 bg-background/70">
          <div className="grid gap-0 lg:grid-cols-[0.85fr_1.15fr]">
            <div className="min-w-0 border-b border-border/60 p-5 lg:border-b-0 lg:border-r">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-2">
                {DEMO_TEMPLATES.map((template) => (
                  <Button
                    key={template.id}
                    type="button"
                    variant={selected.id === template.id ? "default" : "outline"}
                    className="justify-start font-mono"
                    onClick={() => {
                      setSelectedId(template.id);
                      setRunCount(0);
                      trackLandingEvent("demo_template_select", {
                        template: template.id,
                      });
                    }}
                  >
                    {template.label}
                  </Button>
                ))}
              </div>

              <div className="mt-6 space-y-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                    Selected template
                  </p>
                  <h3 className="mt-2 text-xl font-semibold">{selected.title}</h3>
                </div>
                <ProofField label="inputs" value={selected.input} />
                <ProofField label="estimated cost" value={selected.cost} />
                <ProofField label="output" value={selected.outputDetail} />
                <Button
                  type="button"
                  className="w-full font-mono"
                  onClick={() => {
                    setRunCount((value) => value + 1);
                    trackLandingEvent("demo_render_click", {
                      template: selected.id,
                      cache_state: cacheHit ? "hit" : "miss",
                    });
                  }}
                >
                  <RefreshCcw className="mr-2 h-4 w-4" />
                  {cacheHit ? "Run same inputs again" : "Run deterministic render"}
                </Button>
              </div>
            </div>

            <div className="min-w-0 p-5">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                    Result
                  </p>
                  <p className="mt-1 font-mono text-sm">{selected.url}</p>
                </div>
                <Badge
                  variant={cacheHit ? "default" : "outline"}
                  className="font-mono text-[10px]"
                >
                  {cacheHit ? "cache hit · no rebill" : "cache miss · bill once"}
                </Badge>
              </div>

              <div className="grid min-w-0 gap-4 md:grid-cols-[1fr_0.85fr] md:items-stretch">
                <DemoPreview template={selected} />
                <div className="min-w-0 rounded-md border border-border/60 bg-card/50 p-4">
                  <p className="mb-3 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                    Production receipt
                  </p>
                  <div className="space-y-3">
                    <ProofMetric label="job_id" value={`job_${selected.id}_91724`} />
                    <ProofMetric label="credits" value={cacheHit ? "0 cached" : selected.cost} />
                    <ProofMetric label="callback" value="delivered" />
                    <ProofMetric label="gallery" value="saved private" />
                  </div>
                  <div className="mt-5 rounded-md border border-border/60 bg-background/70 p-3">
                    <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                      <Copy className="h-3.5 w-3.5" />
                      API shape
                    </div>
                    <pre className="overflow-x-auto text-xs leading-5">
                      {`POST /v1/render/${selected.apiPath}
{ "seed": 91724 }`}
                    </pre>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function DemoPreview({ template }: { template: DemoTemplate }) {
  if (template.id === "audio") {
    return (
      <div className="flex min-h-72 min-w-0 flex-col justify-between rounded-md border border-border/60 bg-background p-5">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary">
            {template.outputTitle}
          </p>
          <h3 className="mt-3 text-2xl font-bold">Parametric signal rendered</h3>
        </div>
        <div className="flex h-28 items-end gap-1">
          {Array.from({ length: 26 }).map((_, index) => (
            <span
              key={index}
              className="flex-1 rounded-t bg-primary/70"
              style={{ height: `${24 + ((index * 17) % 72)}%` }}
            />
          ))}
        </div>
        <p className="text-sm text-muted-foreground">{template.outputDetail}</p>
      </div>
    );
  }

  if (template.id === "plate") {
    return (
      <div className="flex min-h-72 min-w-0 flex-col items-center justify-center rounded-md border border-border/60 bg-[linear-gradient(145deg,#030712,#111827)] p-5">
        <div className="h-36 w-56 rotate-[-8deg] rounded-2xl border border-primary/50 bg-[linear-gradient(135deg,#1f2937,#020617)] shadow-2xl shadow-primary/20" />
        <h3 className="mt-8 text-xl font-bold">{template.outputTitle}</h3>
        <p className="mt-2 text-sm text-muted-foreground">{template.outputDetail}</p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "min-h-72 min-w-0 rounded-md border border-border/60 p-5",
        template.id === "thumbnail"
          ? "bg-[linear-gradient(135deg,#111827,#0f766e_52%,#f59e0b)]"
          : "bg-[linear-gradient(145deg,#111827,#1f2937_45%,#7c2d12)]",
      )}
    >
      <div className="flex h-full min-h-64 flex-col justify-between rounded-md border border-white/20 bg-black/25 p-5">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary">
            {template.outputDetail}
          </p>
          <h3 className="mt-4 max-w-xs text-3xl font-bold leading-tight">
            {template.outputTitle}
          </h3>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="h-16 rounded-md bg-white/20" />
          <div className="h-16 rounded-md bg-primary/40" />
          <div className="h-16 rounded-md bg-white/10" />
        </div>
      </div>
    </div>
  );
}

function EngineSection() {
  return (
    <section className="border-b border-border/50">
      <div className="mx-auto max-w-6xl px-6 py-16 md:py-20">
        <div className="mb-10 max-w-3xl">
          <p className="mb-3 text-sm font-mono text-primary">› what powers it</p>
          <h2 className="mb-4 text-3xl font-bold tracking-tight md:text-4xl">
            The control plane for generative production work.
          </h2>
          <p className="text-base leading-7 text-muted-foreground">
            CEQ is not a Midjourney clone with extra buttons. It is the pipeline layer
            MADFAM uses to turn reusable templates into shipped product assets.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {ENGINE_FEATURES.map((feature) => {
            const Icon = feature.icon;
            return (
              <Card
                key={feature.title}
                className="border-border/50 bg-card/50 transition-colors hover:border-primary/50"
              >
                <CardContent className="p-5">
                  <Icon className="mb-3 h-5 w-5 text-primary" />
                  <h3 className="mb-2 font-semibold">{feature.title}</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {feature.body}
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
    <section id="pricing" className="border-b border-border/50 bg-card/25">
      <div className="mx-auto max-w-6xl px-6 py-16 md:py-20">
        <div className="mb-10 max-w-3xl">
          <p className="mb-3 text-sm font-mono text-primary">› pricing</p>
          <h2 className="mb-4 text-3xl font-bold tracking-tight md:text-4xl">
            Start free. Reserve paid production capacity before your next deadline.
          </h2>
          <p className="text-base leading-7 text-muted-foreground">
            Credits make CEQ easier to budget than raw GPU time. Paid checkout is coming
            as entitlement proof is completed, so founders reserve access now to lock
            first-run priority and pricing.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          {TIERS.map((tier) => (
            <PricingCard key={tier.name} tier={tier} />
          ))}
        </div>

        <p className="mt-8 text-center text-xs font-mono text-muted-foreground">
          Cache hits reuse the stable output URL and do not consume another render
          charge. Founding-member pricing locks in for life once billing opens; pilots
          are processed in order of reservation.
        </p>
      </div>
    </section>
  );
}

function PricingCard({ tier }: { tier: (typeof TIERS)[number] }) {
  return (
    <Card
      className={cn(
        "relative flex flex-col border-border/50 bg-background/50",
        tier.highlight && "border-primary/60 shadow-lg shadow-primary/10",
      )}
    >
      {tier.highlight && (
        <Badge className="absolute -top-3 left-1/2 -translate-x-1/2 font-mono text-[10px]">
          Highest intent
        </Badge>
      )}
      {tier.pill ? (
        <Badge variant="outline" className="absolute right-4 top-4 text-[10px]">
          {tier.pill}
        </Badge>
      ) : null}
      <CardContent className="flex flex-1 flex-col gap-4 p-6">
        <div>
          <h3 className="font-mono text-lg font-bold">{tier.name}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{tier.blurb}</p>
        </div>
        <div>
          <div className="flex items-baseline gap-1">
            <span className="text-3xl font-bold tracking-tight">{tier.price}</span>
            <span className="text-sm text-muted-foreground">{tier.period}</span>
          </div>
          <p className="mt-2 text-xs font-mono text-primary">
            {tier.credits} · {tier.volume}
          </p>
        </div>
        <ul className="mt-2 flex flex-1 flex-col gap-2">
          {tier.features.map((feature) => (
            <li key={feature} className="flex items-start gap-2 text-sm">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <span className="text-muted-foreground">{feature}</span>
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
        onClick={() => {
          trackLandingEvent("pricing_start_free_click", { tier: tierName });
          startSignIn(cta.href, login);
        }}
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
        onClick={() => {
          trackLandingEvent("pricing_interest_open", { tier: tierName });
          setOpen(true);
        }}
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
    trackLandingEvent("interest_submit_attempt", {
      feature_key: featureKey,
      tier: tierName,
    });
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
      trackLandingEvent("interest_submit_success", {
        feature_key: featureKey,
        tier: tierName,
      });
      setState("ok");
    } catch (e) {
      setState("err");
      setErrMsg(e instanceof Error ? e.message : "Network error");
      trackLandingEvent("interest_submit_error", {
        feature_key: featureKey,
        tier: tierName,
      });
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <Card
        className="w-full max-w-md border-primary/40 bg-card"
        onClick={(event) => event.stopPropagation()}
      >
        <CardContent className="flex flex-col gap-4 p-6">
          {state !== "ok" ? (
            <>
              <div>
                <h3 className="text-lg font-bold font-mono">
                  Reserve {tierName} founding access
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  Tell us what you need CEQ to replace. We will prioritize high-intent
                  production teams and lock founder pricing before checkout
                  opens.
                </p>
              </div>
              <div className="flex flex-col gap-3">
                <Input
                  type="email"
                  placeholder="you@studio.tld"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  disabled={isAuthenticated}
                  className="font-mono"
                />
                <Textarea
                  placeholder="What workflow should CEQ replace for you?"
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  rows={3}
                  className="font-mono text-sm"
                />
                {state === "err" && (
                  <p className="text-xs font-mono text-destructive">{errMsg}</p>
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
                        Reserve access
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
            <div className="flex flex-col items-center gap-3 py-4 text-center">
              <div className="rounded-full bg-primary/10 p-3">
                <Check className="h-6 w-6 text-primary" />
              </div>
              <h3 className="text-lg font-bold font-mono">Founding interest captured.</h3>
              <p className="text-sm text-muted-foreground">
                We will email <span className="font-mono text-foreground">{email}</span>{" "}
                when {tierName} onboarding opens.
              </p>
              <Button onClick={onClose} className="mt-2 w-full font-mono">
                Close
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function TrustSection() {
  return (
    <section className="border-b border-border/50">
      <div className="mx-auto max-w-6xl px-6 py-16 md:py-20">
        <div className="mb-10 max-w-3xl">
          <p className="mb-3 text-sm font-mono text-primary">› buyer safety</p>
          <h2 className="mb-4 text-3xl font-bold tracking-tight md:text-4xl">
            Built for work you would actually show a client.
          </h2>
          <p className="text-base leading-7 text-muted-foreground">
            CEQ is opinionated about privacy, repeatability, and operational audit
            because production teams need more than a beautiful first draft.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {TRUST_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.title}
                className="rounded-md border border-border/50 bg-card/45 p-5"
              >
                <Icon className="mb-3 h-5 w-5 text-primary" />
                <h3 className="font-semibold">{item.title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.body}</p>
              </div>
            );
          })}
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          {[
            ["Terms", "/legal/terms"],
            ["Privacy", "/legal/privacy"],
            ["Acceptable use", "/legal/acceptable-use"],
            ["Retention", "/legal/retention"],
            ["Refunds", "/legal/refunds"],
          ].map(([label, href]) => (
            <Button key={href} asChild variant="outline" size="sm">
              <Link href={href}>
                {label}
                <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            </Button>
          ))}
        </div>
      </div>
    </section>
  );
}

function FAQSection() {
  return (
    <section className="border-b border-border/50 bg-card/25">
      <div className="mx-auto max-w-3xl px-6 py-16 md:py-20">
        <p className="mb-3 text-sm font-mono text-primary">› practical questions</p>
        <h2 className="mb-10 text-3xl font-bold tracking-tight md:text-4xl">
          The questions serious buyers ask before adopting a production tool.
        </h2>
        <div className="flex flex-col gap-4">
          {FAQS.map((faq) => (
            <details
              key={faq.q}
              className="group rounded-md border border-border/50 bg-background/55 p-5 transition-colors hover:border-primary/50"
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold">
                <span>{faq.q}</span>
                <span className="font-mono text-lg text-primary transition-transform group-open:rotate-45">
                  +
                </span>
              </summary>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{faq.a}</p>
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
    <section className="border-b border-border/50">
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-5 px-6 py-16 text-center md:py-20">
        <BadgeCheck className="h-8 w-8 text-primary" />
        <h2 className="text-3xl font-bold tracking-tight md:text-4xl">
          Stop treating generative production like a lucky prompt session.
        </h2>
        <p className="max-w-xl text-base leading-7 text-muted-foreground">
          Start with 100 free credits. If CEQ does not replace at least one brittle
          asset workflow in your stack within 30 minutes, you owe us nothing.
        </p>
        <div className="mt-2 flex flex-col gap-3 sm:flex-row">
          <Button
            onClick={() => {
              trackLandingEvent("final_start_free_click");
              startSignIn("/", login);
            }}
            size="lg"
            className="font-mono"
          >
            Start generating free
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
          <Link href="#demo" onClick={() => trackLandingEvent("final_demo_click")}>
            <Button size="lg" variant="outline" className="w-full font-mono sm:w-auto">
              See the workflow
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
      <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-4 px-6 py-10 md:flex-row md:items-center">
        <div className="flex flex-col gap-1">
          <span className="font-mono text-sm font-bold gradient-text">ceq</span>
          <span className="text-xs font-mono text-muted-foreground">
            Signal acquired. © {new Date().getFullYear()}{" "}
            <a
              href="https://madfam.io"
              target="_blank"
              rel="noopener noreferrer"
              className="transition-colors hover:text-foreground"
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
            className="transition-colors hover:text-foreground"
          >
            GitHub
          </a>
          <a
            href="https://api.ceq.lol/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="transition-colors hover:text-foreground"
          >
            API docs
          </a>
          <Link href="/templates" className="transition-colors hover:text-foreground">
            Templates
          </Link>
          <Link href="/billing" className="transition-colors hover:text-foreground">
            Billing
          </Link>
          <a
            href="https://status.madfam.io"
            target="_blank"
            rel="noopener noreferrer"
            className="transition-colors hover:text-foreground"
          >
            Status
          </a>
        </div>
      </div>
    </footer>
  );
}
