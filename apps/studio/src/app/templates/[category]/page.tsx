"use client";

/**
 * Template Category Page
 *
 * Lists all templates in a category with filtering and search.
 */

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, Loader2, Search, Instagram, Video, Box, Wrench } from "lucide-react";

import { MainLayout } from "@/components/layout/main-layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TemplateCard } from "@/components/templates/template-card";
import { InterestGate } from "@/components/InterestGate";
import { getTemplates, type Template } from "@/lib/api";

/**
 * Premium templates: tagged "pro" or "premium" in the backend.
 * Until paid checkout ships, free users see InterestGate (email capture)
 * over these instead of a 403. Free templates render as usual.
 */
function isPremiumTemplate(template: Template): boolean {
  return template.tags.some((tag) =>
    ["pro", "premium"].includes(tag.toLowerCase())
  );
}

const CATEGORY_META: Record<
  string,
  { title: string; description: string; icon: React.ComponentType<{ className?: string }> }
> = {
  social: {
    title: "Social Media Templates",
    description: "Workflows optimized for social content creation",
    icon: Instagram,
  },
  video: {
    title: "Video Production Templates",
    description: "Video generation and editing workflows",
    icon: Video,
  },
  "3d": {
    title: "3D Rendering Templates",
    description: "3D model generation and rendering pipelines",
    icon: Box,
  },
  utility: {
    title: "Utility Templates",
    description: "General-purpose image and content workflows",
    icon: Wrench,
  },
};

export default function TemplateCategoryPage() {
  const params = useParams();
  const category = params.category as string;
  const [searchQuery, setSearchQuery] = useState("");

  const meta = CATEGORY_META[category] || {
    title: `${category} Templates`,
    description: `Templates in the ${category} category`,
    icon: Box,
  };

  const Icon = meta.icon;

  const { data, isLoading, error } = useQuery({
    queryKey: ["templates", category],
    queryFn: () => getTemplates({ category, limit: 50 }),
    enabled: !!category,
  });

  const templates = data?.templates || [];

  // Filter templates by search query
  const filteredTemplates = templates.filter(
    (t) =>
      t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.tags.some((tag) => tag.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <MainLayout>
      <div className="flex flex-col gap-6 p-6">
        {/* Header */}
        <header>
          <Link href="/templates">
            <Button variant="ghost" size="sm" className="mb-4">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to Templates
            </Button>
          </Link>
          <div className="flex items-center gap-3 mb-2">
            <Icon className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">{meta.title}</h1>
          </div>
          <p className="text-sm text-muted-foreground terminal-text">
            {meta.description}
          </p>
        </header>

        {/* Search */}
        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search templates..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          <span className="text-sm text-muted-foreground">
            {filteredTemplates.length} template{filteredTemplates.length !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="ceq-card text-center py-12">
            <p className="text-destructive mb-2">Failed to load templates</p>
            <p className="text-sm text-muted-foreground">
              {error instanceof Error ? error.message : "Unknown error occurred"}
            </p>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !error && filteredTemplates.length === 0 && (
          <section className="ceq-card">
            <div className="text-center py-12 text-muted-foreground">
              <Icon className="h-12 w-12 mx-auto mb-4 opacity-50" />
              {searchQuery ? (
                <>
                  <p className="terminal-text">No templates match your search.</p>
                  <p className="text-sm">Try a different search term.</p>
                </>
              ) : (
                <>
                  <p className="terminal-text">Templates loading from the void...</p>
                  <p className="text-sm">Templates will appear here once configured.</p>
                </>
              )}
            </div>
          </section>
        )}

        {/* Template grid */}
        {!isLoading && !error && filteredTemplates.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filteredTemplates.map((template) =>
              isPremiumTemplate(template) ? (
                // Pro template: wrap with InterestGate (email capture instead of paywall).
                <InterestGate
                  key={template.id}
                  featureKey="premium_render"
                  variant="overlay"
                  sourcePage={`templates/${category}`}
                  className="h-full"
                >
                  <TemplateCard template={template} />
                </InterestGate>
              ) : (
                <TemplateCard key={template.id} template={template} />
              )
            )}
          </div>
        )}
      </div>
    </MainLayout>
  );
}
