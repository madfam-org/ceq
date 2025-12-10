import { Suspense } from "react";
import { MainLayout } from "@/components/layout/main-layout";
import { QueueMonitor } from "@/components/queue/queue-monitor";
import { Activity } from "lucide-react";

export default function QueuePage() {
  return (
    <MainLayout>
      <div className="flex flex-col gap-6 p-6">
        <header>
          <div className="flex items-center gap-3 mb-2">
            <Activity className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">Queue</h1>
          </div>
          <p className="text-sm text-muted-foreground terminal-text">
            Monitor active transmutations in the furnace
          </p>
        </header>

        <section className="ceq-card">
          <Suspense fallback={<QueueSkeleton />}>
            <QueueMonitor />
          </Suspense>
        </section>
      </div>
    </MainLayout>
  );
}

function QueueSkeleton() {
  return (
    <div className="space-y-3">
      {[...Array(8)].map((_, i) => (
        <div key={i} className="h-12 bg-muted rounded-md shimmer" />
      ))}
    </div>
  );
}
