import { Suspense } from "react";
import { MainLayout } from "@/components/layout/main-layout";
import { WorkflowList } from "@/components/workflows/workflow-list";
import { Workflow, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function WorkflowsPage() {
  return (
    <MainLayout>
      <div className="flex flex-col gap-6 p-6">
        <header className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <Workflow className="h-6 w-6 text-primary" />
              <h1 className="text-2xl font-bold">Workflows</h1>
            </div>
            <p className="text-sm text-muted-foreground terminal-text">
              Manage your entropy transmutation pipelines
            </p>
          </div>
          <Button>
            <Plus className="h-4 w-4 mr-2" />
            New Workflow
          </Button>
        </header>

        <section className="ceq-card">
          <Suspense fallback={<WorkflowListSkeleton />}>
            <WorkflowList />
          </Suspense>
        </section>
      </div>
    </MainLayout>
  );
}

function WorkflowListSkeleton() {
  return (
    <div className="space-y-3">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="h-16 bg-muted rounded-md shimmer" />
      ))}
    </div>
  );
}
