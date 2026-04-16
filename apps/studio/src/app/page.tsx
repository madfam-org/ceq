import { Suspense } from "react";
import { MainLayout } from "@/components/layout/main-layout";
import { WorkflowList } from "@/components/workflows/workflow-list";
import { QueueMonitor } from "@/components/queue/queue-monitor";
import { QuickActions } from "@/components/quick-actions";

export default function HomePage() {
  return (
    <MainLayout>
      <div className="flex flex-col gap-6 p-6">
        {/* Header */}
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold gradient-text">ceq</h1>
            <p className="text-sm text-muted-foreground terminal-text">
              Creative Entropy Quantized
            </p>
          </div>
          <QuickActions />
        </header>

        {/* Main content grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Workflows - 2 columns */}
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

          {/* Queue Monitor - 1 column */}
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

        {/* Status bar */}
        <footer className="fixed bottom-0 left-0 right-0 bg-card border-t border-border px-4 py-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground font-mono">
            <span>Signal acquired.</span>
            <span>
              &copy; {new Date().getFullYear()} CEQ Studio. By{' '}
              <a href="https://madfam.io" className="text-muted-foreground hover:text-foreground transition-colors" target="_blank" rel="noopener noreferrer">Innovaciones MADFAM</a>
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
