"use client";

/**
 * Benchmarks Aggregator
 *
 * A best-value / SOTA tracker for open media-generation models across every
 * modality ceq cares about (image, video, 3D, VLM, TTS, music). Grouped by
 * modality, each model shows its license class (color-coded), VRAM footprint,
 * ComfyUI readiness, and "best at", with client-side filtering. Licensing risk
 * is surfaced prominently — it is the dominant real-world signal.
 *
 * Seed data + scoring live in @/lib/benchmarks (pure, refresh-job-ready).
 */

import { useMemo, useState } from "react";
import {
  Gauge,
  Cpu,
  ShieldCheck,
  AlertTriangle,
  Zap,
  Star,
  ExternalLink,
  Filter,
} from "lucide-react";

import { MainLayout } from "@/components/layout/main-layout";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import {
  BENCHMARK_MODELS,
  COMFY_RATING_LABELS,
  LICENSE_CLASS_LABELS,
  MODALITY_LABELS,
  MODALITY_ORDER,
  TIER_LABELS,
  bestValueScore,
  groupByModality,
  licenseSignal,
  runsInComfyUI,
  type BenchmarkModel,
  type LicenseSignal,
  type Modality,
} from "@/lib/benchmarks";

const LICENSE_SIGNAL_CLASSES: Record<LicenseSignal, string> = {
  green: "border-green-500/40 bg-green-500/10 text-green-400",
  amber: "border-amber-500/40 bg-amber-500/10 text-amber-400",
  red: "border-destructive/40 bg-destructive/10 text-destructive",
};

function LicenseBadge({ model }: { model: BenchmarkModel }) {
  const signal = licenseSignal(model.licenseClass);
  return (
    <span
      title={model.license}
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium",
        LICENSE_SIGNAL_CLASSES[signal],
      )}
    >
      <ShieldCheck className="h-3 w-3" />
      {LICENSE_CLASS_LABELS[model.licenseClass]}
    </span>
  );
}

function ComfyBadge({ model }: { model: BenchmarkModel }) {
  const isDropIn = model.comfyuiRating === "drop-in";
  const isApiOnly = model.comfyuiRating === "api-only";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-mono",
        isDropIn
          ? "border-primary/40 bg-primary/10 text-primary"
          : isApiOnly
            ? "border-destructive/40 bg-destructive/10 text-destructive"
            : "border-border bg-muted text-muted-foreground",
      )}
    >
      <Cpu className="h-3 w-3" />
      {COMFY_RATING_LABELS[model.comfyuiRating]}
    </span>
  );
}

function TierPill({ model }: { model: BenchmarkModel }) {
  if (model.tier === "standardize-now") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-primary/50 bg-primary/15 px-2 py-0.5 text-xs font-semibold text-primary">
        <Star className="h-3 w-3" />
        {TIER_LABELS[model.tier]}
      </span>
    );
  }
  if (model.tier === "efficiency-pick") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-green-500/50 bg-green-500/15 px-2 py-0.5 text-xs font-semibold text-green-400">
        <Zap className="h-3 w-3" />
        {TIER_LABELS[model.tier]}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
      {TIER_LABELS[model.tier]}
    </span>
  );
}

function ModelCard({ model }: { model: BenchmarkModel }) {
  const highlighted =
    model.tier === "standardize-now" || model.tier === "efficiency-pick";
  const score = bestValueScore(model);
  return (
    <div
      className={cn(
        "ceq-card flex flex-col gap-3",
        highlighted
          ? model.tier === "efficiency-pick"
            ? "border-green-500/40"
            : "border-primary/40"
          : "opacity-90",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-semibold leading-tight">{model.name}</h3>
          <p className="text-xs text-muted-foreground">{model.maker}</p>
        </div>
        <TierPill model={model} />
      </div>

      <p className="text-sm text-muted-foreground">{model.bestAt}</p>

      <div className="flex flex-wrap gap-2">
        <LicenseBadge model={model} />
        <ComfyBadge model={model} />
        <span className="inline-flex items-center gap-1 rounded-md border border-border bg-muted px-2 py-0.5 text-xs font-mono text-muted-foreground">
          <Gauge className="h-3 w-3" />
          {model.vramGb == null ? "CPU-capable" : `${model.vramGb}GB fp16`}
        </span>
      </div>

      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">VRAM / quant</dt>
          <dd className="terminal-text">{model.vramNote}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Speed</dt>
          <dd className="terminal-text">{model.speedNote}</dd>
        </div>
      </dl>

      {model.riskFlag ? (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs text-amber-300/90">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
          <span>{model.riskFlag}</span>
        </div>
      ) : null}

      <div className="mt-auto flex items-center justify-between border-t border-border pt-2 text-xs text-muted-foreground">
        <span className="font-mono">
          best-value{" "}
          <span className="text-foreground">{score}</span>
          <span className="opacity-60">/100</span>
        </span>
        <a
          href={model.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 hover:text-primary"
        >
          source
          <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    </div>
  );
}

export default function BenchmarksPage() {
  const [modalityFilter, setModalityFilter] = useState<Modality | "all">("all");
  const [commercialOnly, setCommercialOnly] = useState(false);
  const [comfyOnly, setComfyOnly] = useState(false);

  const filtered = useMemo(() => {
    return BENCHMARK_MODELS.filter((model) => {
      if (modalityFilter !== "all" && model.modality !== modalityFilter)
        return false;
      if (commercialOnly && !model.commercialOk) return false;
      if (comfyOnly && !runsInComfyUI(model)) return false;
      return true;
    });
  }, [modalityFilter, commercialOnly, comfyOnly]);

  const groups = useMemo(() => groupByModality(filtered), [filtered]);

  const totalCount = BENCHMARK_MODELS.length;
  const shownCount = filtered.length;

  return (
    <MainLayout>
      <div className="flex flex-col gap-6 p-6">
        <header>
          <div className="mb-2 flex items-center gap-3">
            <Gauge className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">Benchmarks</h1>
          </div>
          <p className="text-sm text-muted-foreground terminal-text">
            Best-value, SOTA open models across every media-generation type —
            what runs in ComfyUI today, with the licensing traps surfaced.
          </p>
        </header>

        {/* Legend */}
        <div className="ceq-card flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Star className="h-3 w-3 text-primary" /> Standardize now
          </span>
          <span className="inline-flex items-center gap-1">
            <Zap className="h-3 w-3 text-green-400" /> Efficiency sweet spot
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-full bg-green-500/60" />
            Commercial-clean license
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-full bg-amber-500/60" />
            Gated (revenue / geo)
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-full bg-destructive/60" />
            Non-commercial / API-only
          </span>
        </div>

        {/* Filters */}
        <div className="ceq-card flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-1 inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Filter className="h-3.5 w-3.5" /> Modality
            </span>
            <button
              type="button"
              onClick={() => setModalityFilter("all")}
              className={cn(
                "rounded-md border px-2.5 py-1 text-xs font-mono transition-colors",
                modalityFilter === "all"
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground",
              )}
            >
              All
            </button>
            {MODALITY_ORDER.map((modality) => (
              <button
                key={modality}
                type="button"
                onClick={() => setModalityFilter(modality)}
                className={cn(
                  "rounded-md border px-2.5 py-1 text-xs font-mono transition-colors",
                  modalityFilter === modality
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground",
                )}
              >
                {MODALITY_LABELS[modality]}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-6">
            <label className="flex cursor-pointer items-center gap-2 text-xs">
              <Switch
                checked={commercialOnly}
                onCheckedChange={setCommercialOnly}
                aria-label="Commercial-safe only"
              />
              <span className="text-muted-foreground">Commercial-safe only</span>
            </label>
            <label className="flex cursor-pointer items-center gap-2 text-xs">
              <Switch
                checked={comfyOnly}
                onCheckedChange={setComfyOnly}
                aria-label="Runs in ComfyUI"
              />
              <span className="text-muted-foreground">Runs in ComfyUI</span>
            </label>
          </div>
        </div>

        <p className="text-xs text-muted-foreground">
          Showing{" "}
          <span className="font-mono text-foreground">{shownCount}</span> of{" "}
          <span className="font-mono text-foreground">{totalCount}</span> tracked
          models. Speed / VRAM figures are vendor / community numbers — re-measure
          on ceq&apos;s own GPU workers.
        </p>

        {groups.length === 0 ? (
          <div className="ceq-card py-12 text-center text-muted-foreground">
            <AlertTriangle className="mx-auto mb-4 h-12 w-12 opacity-50" />
            <p className="terminal-text">No models match those filters.</p>
          </div>
        ) : (
          groups.map((group) => (
            <section key={group.modality} className="flex flex-col gap-3">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <span className="text-primary">›</span>
                {group.label}
                <span className="text-xs font-mono text-muted-foreground">
                  {group.models.length}
                </span>
              </h2>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                {group.models.map((model) => (
                  <ModelCard key={model.id} model={model} />
                ))}
              </div>
            </section>
          ))
        )}
      </div>
    </MainLayout>
  );
}
