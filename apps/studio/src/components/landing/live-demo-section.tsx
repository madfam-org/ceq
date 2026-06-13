"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  Copy,
  Loader2,
  RefreshCcw,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/auth-context";
import { cn } from "@/lib/utils";
import {
  DEMO_SIGNUP_RETURN_TO,
  type DemoPresetId,
  type DemoPresetInfo,
  type DemoRenderResult,
  fetchDemoPresets,
  runDemoRender,
  startSignIn,
  trackLandingEvent,
} from "@/lib/landing-demo";

interface LiveDemoSectionProps {
  onEngagement?: () => void;
}

export function LiveDemoSection({ onEngagement }: LiveDemoSectionProps) {
  const { login } = useAuth();
  const [presets, setPresets] = useState<DemoPresetInfo[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<DemoPresetId>("card");
  const [result, setResult] = useState<DemoRenderResult | null>(null);
  const [runState, setRunState] = useState<"idle" | "loading" | "error">("idle");
  const [runError, setRunError] = useState<string | null>(null);
  const [hasRendered, setHasRendered] = useState(false);

  useEffect(() => {
    fetchDemoPresets()
      .then(setPresets)
      .catch((error: Error) => setLoadError(error.message));
  }, []);

  const selected =
    presets.find((preset) => preset.id === selectedId) ??
    presets[0] ??
    null;

  const executeRender = useCallback(async () => {
    if (!selected) return;
    setRunState("loading");
    setRunError(null);
    trackLandingEvent("demo_render_click", {
      template: selected.id,
      cache_state: result ? "hit" : "miss",
    });
    try {
      const response = await runDemoRender(selected.id);
      setResult(response);
      setHasRendered(true);
      setRunState("idle");
      onEngagement?.();
      trackLandingEvent("demo_render_success", {
        template: selected.id,
        cached: response.cached,
      });
    } catch (error) {
      setRunState("error");
      setRunError(error instanceof Error ? error.message : "Render failed");
      trackLandingEvent("demo_render_error", { template: selected.id });
    }
  }, [onEngagement, result, selected]);

  const cacheHit = Boolean(result?.cached);

  return (
    <section id="demo" className="border-b border-border/50 bg-card/25">
      <div className="mx-auto max-w-6xl px-6 py-16 md:py-20">
        <div className="mb-10 max-w-3xl">
          <p className="mb-3 text-sm font-mono text-primary">› try the production loop</p>
          <h2 className="mb-4 text-3xl font-bold tracking-tight md:text-4xl">
            Template, render, reuse. Live on CEQ production API.
          </h2>
          <p className="text-base leading-7 text-muted-foreground">
            Run real deterministic renders against{" "}
            <span className="font-mono text-foreground">api.ceq.lol</span> — no
            account required for this preview. Identical inputs resolve to the same
            cached URL; cache hits do not rebill credits when you sign up.
          </p>
        </div>

        {loadError && (
          <p className="mb-4 text-sm font-mono text-destructive">{loadError}</p>
        )}

        <div className="overflow-hidden rounded-lg border border-primary/25 bg-background/70">
          <div className="grid gap-0 lg:grid-cols-[0.85fr_1.15fr]">
            <div className="min-w-0 border-b border-border/60 p-5 lg:border-b-0 lg:border-r">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-2">
                {(presets.length ? presets : [{ id: "card" as const, label: "Card" }]).map(
                  (template) => (
                    <Button
                      key={template.id}
                      type="button"
                      variant={selected?.id === template.id ? "default" : "outline"}
                      className="justify-start font-mono"
                      disabled={!presets.length}
                      onClick={() => {
                        setSelectedId(template.id);
                        setResult(null);
                        setRunState("idle");
                        setRunError(null);
                        trackLandingEvent("demo_template_select", {
                          template: template.id,
                        });
                      }}
                    >
                      {"label" in template ? template.label : "Card"}
                    </Button>
                  ),
                )}
              </div>

              {selected && (
                <div className="mt-6 space-y-4">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                      Selected template
                    </p>
                    <h3 className="mt-2 text-xl font-semibold">{selected.title}</h3>
                  </div>
                  <ProofField label="inputs" value={selected.input_summary} />
                  <ProofField
                    label="estimated cost"
                    value={`${selected.credit_cost} credits`}
                  />
                  <ProofField label="output" value={selected.output_summary} />
                  <Button
                    type="button"
                    className="w-full font-mono"
                    disabled={runState === "loading"}
                    onClick={() => void executeRender()}
                  >
                    {runState === "loading" ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Rendering…
                      </>
                    ) : (
                      <>
                        <RefreshCcw className="mr-2 h-4 w-4" />
                        {result ? "Run same inputs again" : "Run live render"}
                      </>
                    )}
                  </Button>
                  {runError && (
                    <p className="text-xs font-mono text-destructive">{runError}</p>
                  )}
                </div>
              )}
            </div>

            <div className="min-w-0 p-5">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                    Result
                  </p>
                  <p className="mt-1 truncate font-mono text-sm">
                    {result?.storage_uri ?? "Run a render to materialize output"}
                  </p>
                </div>
                <Badge
                  variant={result ? (cacheHit ? "default" : "outline") : "outline"}
                  className="font-mono text-[10px]"
                >
                  {!result
                    ? "awaiting run"
                    : cacheHit
                      ? "cache hit · no rebill"
                      : "cache miss · bill once"}
                </Badge>
              </div>

              <div className="grid min-w-0 gap-4 md:grid-cols-[1fr_0.85fr] md:items-stretch">
                <DemoAssetPreview preset={selected} result={result} loading={runState === "loading"} />
                <div className="min-w-0 rounded-md border border-border/60 bg-card/50 p-4">
                  <p className="mb-3 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                    Production receipt
                  </p>
                  <div className="space-y-3">
                    <ProofMetric
                      label="hash"
                      value={result?.hash?.slice(0, 16) ?? "—"}
                    />
                    <ProofMetric
                      label="credits"
                      value={cacheHit ? "0 cached" : selected ? `${selected.credit_cost}` : "—"}
                    />
                    <ProofMetric label="callback" value={result ? "delivered" : "pending"} />
                    <ProofMetric label="gallery" value="preview only" />
                  </div>
                  <div className="mt-5 rounded-md border border-border/60 bg-background/70 p-3">
                    <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                      <Copy className="h-3.5 w-3.5" />
                      API shape
                    </div>
                    <pre className="overflow-x-auto text-xs leading-5">
                      {selected
                        ? `POST /v1/demo/render/${selected.id}\n→ POST /v1/render/${selected.api_path}`
                        : "POST /v1/demo/render/{preset}"}
                    </pre>
                  </div>
                </div>
              </div>

              {hasRendered && (
                <div className="mt-5 rounded-md border border-primary/30 bg-primary/5 p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="font-mono text-sm font-semibold">
                        Ready to run GPU workflows in Studio?
                      </p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Sign up free — 100 credits, full template library, private gallery.
                      </p>
                    </div>
                    <Button
                      className="font-mono shrink-0"
                      onClick={() => {
                        trackLandingEvent("demo_post_render_signup");
                        startSignIn(DEMO_SIGNUP_RETURN_TO, login);
                      }}
                    >
                      <Sparkles className="mr-2 h-4 w-4" />
                      Start free
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function DemoAssetPreview({
  preset,
  result,
  loading,
}: {
  preset: DemoPresetInfo | null;
  result: DemoRenderResult | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="flex min-h-72 items-center justify-center rounded-md border border-border/60 bg-background/70">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!result?.url) {
    return (
      <div className="flex min-h-72 flex-col items-center justify-center rounded-md border border-dashed border-border/60 bg-background/40 p-6 text-center">
        <p className="font-mono text-sm text-muted-foreground">
          {preset ? `Run ${preset.title} to preview the asset` : "Select a template"}
        </p>
      </div>
    );
  }

  if (result.content_type.startsWith("audio/")) {
    return (
      <div className="flex min-h-72 flex-col justify-between rounded-md border border-border/60 bg-background p-5">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary">
          Live WAV output
        </p>
        <audio controls className="w-full" src={result.url}>
          <track kind="captions" />
        </audio>
        <p className="text-sm text-muted-foreground">{result.content_type}</p>
      </div>
    );
  }

  if (result.content_type.includes("gltf") || result.url.endsWith(".glb")) {
    return (
      <div className="flex min-h-72 flex-col items-center justify-center gap-3 rounded-md border border-border/60 bg-[linear-gradient(145deg,#030712,#111827)] p-5">
        <p className="text-center text-sm text-muted-foreground">
          GLB materialized — open in Studio or your 3D viewer.
        </p>
        <a
          href={result.url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-mono text-sm text-primary underline-offset-4 hover:underline"
        >
          Download {result.hash.slice(0, 8)}.glb
        </a>
      </div>
    );
  }

  return (
    <div className="min-h-72 overflow-hidden rounded-md border border-border/60 bg-background">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={result.url}
        alt={preset?.title ?? "Rendered asset"}
        className="h-full min-h-72 w-full object-cover"
      />
    </div>
  );
}

function ProofField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono text-sm">{value}</p>
    </div>
  );
}

function ProofMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 font-mono text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("truncate text-right", label === "hash" && "max-w-[9rem]")}>
        {value}
      </span>
    </div>
  );
}
