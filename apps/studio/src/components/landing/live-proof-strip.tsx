"use client";

import { useEffect, useState } from "react";
import { Database, Gauge, Repeat2, Sparkles } from "lucide-react";

import { fetchDemoStatus, type DemoStatus } from "@/lib/landing-demo";

const STATIC_PROOF = [
  { label: "100 free credits", detail: "no card required", icon: Sparkles },
  { label: "Deterministic URLs", detail: "same inputs, same asset", icon: Repeat2 },
  { label: "R2-backed cache", detail: "cache hits do not rebill", icon: Database },
  { label: "Studio + SDK", detail: "UI for humans, API for products", icon: Gauge },
];

export function LiveProofStrip() {
  const [status, setStatus] = useState<DemoStatus | null>(null);

  useEffect(() => {
    void fetchDemoStatus().then(setStatus);
  }, []);

  const proof = STATIC_PROOF.map((item, index) => {
    if (index === 3 && status) {
      return {
        ...item,
        detail: `${status.workflow_templates} GPU templates · ${status.render_templates} render presets live`,
      };
    }
    return item;
  });

  return (
    <section className="border-b border-border/50 bg-card/25">
      <div className="mx-auto grid max-w-6xl gap-3 px-6 py-6 md:grid-cols-4">
        {proof.map((item) => {
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
