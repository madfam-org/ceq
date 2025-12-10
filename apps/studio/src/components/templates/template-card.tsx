"use client";

/**
 * Template Card
 *
 * Displays a template preview with metadata and quick actions.
 */

import Link from "next/link";
import Image from "next/image";
import { Cpu, Zap, Play, GitFork } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { Template } from "@/lib/api";

interface TemplateCardProps {
  template: Template;
  className?: string;
}

const categoryColors = {
  social: "bg-pink-500/10 text-pink-500 border-pink-500/20",
  video: "bg-purple-500/10 text-purple-500 border-purple-500/20",
  "3d": "bg-blue-500/10 text-blue-500 border-blue-500/20",
  utility: "bg-green-500/10 text-green-500 border-green-500/20",
};

export function TemplateCard({ template, className }: TemplateCardProps) {
  return (
    <Card
      className={cn(
        "group overflow-hidden transition-all hover:border-signal/50",
        className
      )}
    >
      {/* Thumbnail */}
      <Link href={`/templates/${template.category}/${template.id}`}>
        <div className="relative aspect-video bg-muted overflow-hidden">
          {template.thumbnail_url ? (
            <Image
              src={template.thumbnail_url}
              alt={template.name}
              fill
              className="object-cover transition-transform group-hover:scale-105"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-4xl opacity-20">
                {getCategoryEmoji(template.category)}
              </div>
            </div>
          )}

          {/* Overlay on hover */}
          <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
            <Button size="sm" variant="secondary" className="gap-1">
              <Play className="h-3 w-3" />
              Run
            </Button>
            <Button size="sm" variant="outline" className="gap-1">
              <GitFork className="h-3 w-3" />
              Fork
            </Button>
          </div>

          {/* Category badge */}
          <Badge
            variant="outline"
            className={cn(
              "absolute top-2 right-2 capitalize text-xs",
              categoryColors[template.category]
            )}
          >
            {template.category}
          </Badge>
        </div>
      </Link>

      <CardContent className="p-4">
        <Link href={`/templates/${template.category}/${template.id}`}>
          <h3 className="font-medium text-foreground hover:text-signal transition-colors line-clamp-1">
            {template.name}
          </h3>
        </Link>

        {template.description && (
          <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
            {template.description}
          </p>
        )}

        {/* Tags */}
        {template.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-3">
            {template.tags.slice(0, 3).map((tag) => (
              <Badge key={tag} variant="secondary" className="text-xs">
                {tag}
              </Badge>
            ))}
            {template.tags.length > 3 && (
              <Badge variant="secondary" className="text-xs">
                +{template.tags.length - 3}
              </Badge>
            )}
          </div>
        )}
      </CardContent>

      <CardFooter className="px-4 py-3 border-t border-border bg-muted/30">
        <div className="flex items-center justify-between w-full text-xs text-muted-foreground">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <Cpu className="h-3 w-3" />
              {template.vram_requirement_gb}GB
            </span>
            <span className="flex items-center gap-1">
              <Zap className="h-3 w-3" />
              {formatNumber(template.run_count)} runs
            </span>
          </div>
          <span className="flex items-center gap-1">
            <GitFork className="h-3 w-3" />
            {formatNumber(template.fork_count)}
          </span>
        </div>
      </CardFooter>
    </Card>
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

function formatNumber(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}
