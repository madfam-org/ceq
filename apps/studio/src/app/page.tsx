"use client";

import { Suspense } from "react";
import { MainLayout } from "@/components/layout/main-layout";
import { WorkflowList } from "@/components/workflows/workflow-list";
import { QueueMonitor } from "@/components/queue/queue-monitor";
import { QuickActions } from "@/components/quick-actions";
import { MarketingLanding } from "@/components/landing/marketing-landing";
import { useAuth } from "@/contexts/auth-context";

// App-host root page. Reached at app.ceq.lol/. Marketing-host requests
// (ceq.lol/) are rewritten to /landing by middleware — see middleware.ts
// for the why (Cloudflare cached the SSR HTML across hosts and the
// previous client-side window.location.host gate didn't survive that).
export default function HomePage() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="font-mono text-sm text-muted-foreground">
          <span className="text-primary">›</span> acquiring signal…
        </div>
      </div>
    );
  }

  // Unauthenticated visitors on app.ceq.lol see the landing as a soft
  // gate. URL stays "/" so the cache entry is distinct from
  // ceq.lol/landing — no cross-host pollution.
  if (!isAuthenticated) {
    return <MarketingLanding />;
  }

  return (
    <MainLayout>
      <div className="flex flex-col gap-6 p-6">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold gradient-text">ceq</h1>
            <p className="text-sm text-muted-foreground terminal-text">
              Creative Entropy Quantized
            </p>
          </div>
          <QuickActions />
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <section className="ceq-card">
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <span className="text-primary">›</span>
                Workflows
              </h2>
              <Suspense fallback={<WorkflowListSkeleton />}>
                <WorkflowList />
              </Suspense>
            </section>
          </div>

          <div>
            <section className="ceq-card">
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <span className="text-primary">›</span>
                Queue
              </h2>
              <Suspense fallback={<QueueMonitorSkeleton />}>
                <QueueMonitor />
              </Suspense>
            </section>
          </div>
        </div>

        <footer className="fixed bottom-0 left-0 right-0 bg-card border-t border-border px-4 py-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground font-mono">
            <span>Signal acquired.</span>
            <span>
              &copy; {new Date().getFullYear()} CEQ Studio. By{" "}
              <a
                href="https://madfam.io"
                className="text-muted-foreground hover:text-foreground transition-colors"
                target="_blank"
                rel="noopener noreferrer"
              >
                Innovaciones MADFAM
              </a>
            </span>
            <span>ceq v0.1.0 | Entropy: stable</span>
          </div>
        </footer>
      </div>
    </MainLayout>
  );
}

function WorkflowListSkeleton() {
  return (
    <div className="space-y-3">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-16 bg-muted rounded-md shimmer" />
      ))}
    </div>
  );
}

function QueueMonitorSkeleton() {
  return (
    <div className="space-y-3">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="h-12 bg-muted rounded-md shimmer" />
      ))}
    </div>
  );
}
