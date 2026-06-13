"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Loader2, Workflow } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useAuth } from "@/contexts/auth-context";
import {
  DEMO_SIGNUP_RETURN_TO,
  fetchPublicTemplates,
  startSignIn,
  trackLandingEvent,
  type WorkflowTemplateSummary,
} from "@/lib/landing-demo";

export function WorkflowShowcaseSection() {
  const { login } = useAuth();
  const [templates, setTemplates] = useState<WorkflowTemplateSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPublicTemplates(6)
      .then(setTemplates)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section id="templates" className="border-b border-border/50">
      <div className="mx-auto max-w-6xl px-6 py-16 md:py-20">
        <div className="mb-10 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="max-w-3xl">
            <p className="mb-3 text-sm font-mono text-primary">› workflow library</p>
            <h2 className="mb-4 text-3xl font-bold tracking-tight md:text-4xl">
              GPU templates ready to fork and run in Studio.
            </h2>
            <p className="text-base leading-7 text-muted-foreground">
              Browse the public spell library — social, video, 3D, and utility
              workflows. Sign up to fork, queue GPU jobs, and save outputs to your
              private gallery.
            </p>
          </div>
          <Button
            variant="outline"
            className="font-mono shrink-0"
            onClick={() => {
              trackLandingEvent("templates_signup_click");
              startSignIn(DEMO_SIGNUP_RETURN_TO, login);
            }}
          >
            Open full library
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        )}

        {error && (
          <p className="font-mono text-sm text-destructive">{error}</p>
        )}

        {!loading && !error && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {templates.map((template) => (
              <Card
                key={template.id}
                className="border-border/60 bg-card/40 transition-colors hover:border-primary/40"
              >
                <CardContent className="flex h-full flex-col gap-4 p-5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Workflow className="h-4 w-4 text-primary" />
                      <Badge variant="outline" className="font-mono text-[10px]">
                        {template.category}
                      </Badge>
                    </div>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {template.run_count} runs
                    </span>
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold">{template.name}</h3>
                    {template.description && (
                      <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
                        {template.description}
                      </p>
                    )}
                  </div>
                  {template.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {template.tags.slice(0, 3).map((tag) => (
                        <Badge key={tag} variant="secondary" className="font-mono text-[10px]">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  )}
                  <Button
                    className="mt-auto w-full font-mono"
                    variant="secondary"
                    onClick={() => {
                      trackLandingEvent("template_fork_intent", {
                        template_id: template.id,
                        template_name: template.name,
                      });
                      startSignIn(
                        `/templates/${template.id}?onboarding=demo`,
                        login,
                      );
                    }}
                  >
                    Sign up to run
                    <ArrowRight className="ml-2 h-3.5 w-3.5" />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
