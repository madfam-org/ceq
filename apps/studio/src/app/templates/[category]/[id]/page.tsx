"use client";

/**
 * Template Detail Page
 *
 * Shows template info, preview images, and run form.
 */

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, Loader2, AlertCircle } from "lucide-react";

import { MainLayout } from "@/components/layout/main-layout";
import { Button } from "@/components/ui/button";
import { TemplateRunForm } from "@/components/templates/template-run-form";
import { getTemplate } from "@/lib/api";

export default function TemplateDetailPage() {
  const params = useParams();
  const category = params.category as string;
  const templateId = params.id as string;

  const {
    data: template,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["template", templateId],
    queryFn: () => getTemplate(templateId),
    enabled: !!templateId,
  });

  if (isLoading) {
    return (
      <MainLayout>
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="text-center">
            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-primary" />
            <p className="text-muted-foreground terminal-text">
              Materializing template...
            </p>
          </div>
        </div>
      </MainLayout>
    );
  }

  if (error || !template) {
    return (
      <MainLayout>
        <div className="flex flex-col gap-6 p-6">
          <Link href={`/templates/${category}`}>
            <Button variant="ghost" size="sm">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to {category} templates
            </Button>
          </Link>
          <div className="flex flex-col items-center justify-center min-h-[40vh] text-center">
            <AlertCircle className="h-12 w-12 text-destructive mb-4" />
            <h2 className="text-xl font-semibold mb-2">Template not found</h2>
            <p className="text-muted-foreground">
              {error instanceof Error
                ? error.message
                : "The requested template could not be located in the void."}
            </p>
          </div>
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout>
      <div className="flex flex-col gap-6 p-6">
        {/* Back navigation */}
        <Link href={`/templates/${category}`}>
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to {category} templates
          </Button>
        </Link>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left: Preview */}
          <div className="space-y-4">
            {/* Main preview */}
            <div className="aspect-video relative rounded-lg overflow-hidden bg-muted">
              {template.thumbnail_url ? (
                <Image
                  src={template.thumbnail_url}
                  alt={template.name}
                  fill
                  className="object-cover"
                  priority
                />
              ) : (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="text-6xl opacity-20">
                    {getCategoryEmoji(template.category)}
                  </div>
                </div>
              )}
            </div>

            {/* Additional previews */}
            {template.preview_urls.length > 0 && (
              <div className="grid grid-cols-4 gap-2">
                {template.preview_urls.slice(0, 4).map((url, i) => (
                  <div
                    key={i}
                    className="aspect-square relative rounded-md overflow-hidden bg-muted"
                  >
                    <Image
                      src={url}
                      alt={`Preview ${i + 1}`}
                      fill
                      className="object-cover"
                    />
                  </div>
                ))}
              </div>
            )}

            {/* Workflow info */}
            <div className="ceq-card">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <span className="text-primary">›</span>
                Workflow Details
              </h3>
              <dl className="grid grid-cols-2 gap-2 text-sm">
                <dt className="text-muted-foreground">Category</dt>
                <dd className="capitalize">{template.category}</dd>
                <dt className="text-muted-foreground">VRAM Required</dt>
                <dd>{template.vram_requirement_gb}GB</dd>
                <dt className="text-muted-foreground">Total Runs</dt>
                <dd>{template.run_count.toLocaleString()}</dd>
                <dt className="text-muted-foreground">Forks</dt>
                <dd>{template.fork_count.toLocaleString()}</dd>
                <dt className="text-muted-foreground">Created</dt>
                <dd>{new Date(template.created_at).toLocaleDateString()}</dd>
              </dl>
            </div>
          </div>

          {/* Right: Run Form */}
          <div className="ceq-card">
            <TemplateRunForm template={template} />
          </div>
        </div>
      </div>
    </MainLayout>
  );
}

function getCategoryEmoji(category: string): string {
  switch (category) {
    case "social":
      return "🖼️";
    case "video":
      return "🎬";
    case "3d":
      return "🎲";
    case "utility":
      return "🔧";
    default:
      return "📦";
  }
}
