import { MainLayout } from "@/components/layout/main-layout";
import { Layers, Instagram, Video, Box } from "lucide-react";
import Link from "next/link";

const TEMPLATE_CATEGORIES = [
  {
    id: "social",
    title: "Social Media",
    description: "Content optimized for Instagram, TikTok, and social platforms",
    icon: Instagram,
    count: 12,
    href: "/templates/social",
  },
  {
    id: "video",
    title: "Video Production",
    description: "Video generation and editing workflows",
    icon: Video,
    count: 8,
    href: "/templates/video",
  },
  {
    id: "3d",
    title: "3D Rendering",
    description: "3D model generation and rendering pipelines",
    icon: Box,
    count: 5,
    href: "/templates/3d",
  },
];

export default function TemplatesPage() {
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

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {TEMPLATE_CATEGORIES.map((category) => (
            <Link
              key={category.id}
              href={category.href}
              className="ceq-card group hover:border-primary/50 transition-colors"
            >
              <div className="flex items-start gap-4">
                <div className="p-3 rounded-lg bg-primary/10 group-hover:bg-primary/20 transition-colors">
                  <category.icon className="h-6 w-6 text-primary" />
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold mb-1">{category.title}</h3>
                  <p className="text-sm text-muted-foreground mb-2">
                    {category.description}
                  </p>
                  <span className="text-xs font-mono text-primary">
                    {category.count} templates
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>

        <section className="ceq-card">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <span className="text-primary">›</span>
            Recent Templates
          </h2>
          <div className="text-center py-8 text-muted-foreground">
            <Layers className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="terminal-text">No templates loaded yet.</p>
            <p className="text-sm">Browse categories above to explore.</p>
          </div>
        </section>
      </div>
    </MainLayout>
  );
}
