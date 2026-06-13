"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Layers,
  Instagram,
  Video,
  Box,
  Wrench,
  Loader2,
  AlertCircle,
} from "lucide-react";

import { MainLayout } from "@/components/layout/main-layout";
import { TemplateCard } from "@/components/templates/template-card";
import { getTemplates, type Template } from "@/lib/api";

const CATEGORY_META: Record<
  string,
  {
    title: string;
    description: string;
    icon: React.ComponentType<{ className?: string }>;
    href: string;
  }
> = {
  social: {
    title: "Social Media",
    description: "Content optimized for Instagram, TikTok, and social platforms",
    icon: Instagram,
    href: "/templates/social",
  },
  video: {
    title: "Video Production",
    description: "Video generation and editing workflows",
    icon: Video,
    href: "/templates/video",
  },
  "3d": {
    title: "3D Rendering",
    description: "3D model generation and rendering pipelines",
    icon: Box,
    href: "/templates/3d",
  },
  utility: {
    title: "Utility",
    description: "Image processing, upscaling, and enhancement",
    icon: Wrench,
    href: "/templates/utility",
  },
};

function countByCategory(templates: Template[]): Record<string, number> {
  return templates.reduce<Record<string, number>>((counts, template) => {
    counts[template.category] = (counts[template.category] ?? 0) + 1;
    return counts;
  }, {});
}

export default function TemplatesPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["templates", "hub"],
    queryFn: () => getTemplates({ limit: 100 }),
  });

  const templates = data?.templates ?? [];
  const counts = countByCategory(templates);
  const recentTemplates = [...templates]
    .sort((a, b) => {
      const runDelta = (b.run_count ?? 0) - (a.run_count ?? 0);
      if (runDelta !== 0) return runDelta;
      return (
        new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      );
    })
    .slice(0, 6);

  return (
    <MainLayout>
      <div className="flex flex-col gap-6 p-6">
        <header>
          <div className="flex items-center gap-3 mb-2">
            <Layers className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">Templates</h1>
          </div>
          <p className="text-sm text-muted-foreground terminal-text">
            Pre-built workflows for common creative tasks
          </p>
        </header>

        {isLoading ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin mr-2" />
            Loading template catalog…
          </div>
        ) : error ? (
          <div className="ceq-card text-center py-12 text-muted-foreground">
            <AlertCircle className="h-12 w-12 mx-auto mb-4 text-destructive opacity-50" />
            <p className="terminal-text">Signal lost in the noise.</p>
            <p className="text-sm">{(error as Error).message}</p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {Object.entries(CATEGORY_META).map(([id, category]) => {
                const Icon = category.icon;
                const count = counts[id] ?? 0;
                if (count === 0) return null;

                return (
                  <Link
                    key={id}
                    href={category.href}
                    className="ceq-card group hover:border-primary/50 transition-colors"
                  >
                    <div className="flex items-start gap-4">
                      <div className="p-3 rounded-lg bg-primary/10 group-hover:bg-primary/20 transition-colors">
                        <Icon className="h-6 w-6 text-primary" />
                      </div>
                      <div className="flex-1">
                        <h3 className="font-semibold mb-1">{category.title}</h3>
                        <p className="text-sm text-muted-foreground mb-2">
                          {category.description}
                        </p>
                        <span className="text-xs font-mono text-primary">
                          {count} template{count === 1 ? "" : "s"}
                        </span>
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>

            <section className="ceq-card">
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <span className="text-primary">›</span>
                Recent Templates
              </h2>
              {recentTemplates.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {recentTemplates.map((template) => (
                    <TemplateCard key={template.id} template={template} />
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <Layers className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p className="terminal-text">No templates loaded yet.</p>
                  <p className="text-sm">Browse categories above to explore.</p>
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </MainLayout>
  );
}
