"use client";

import { Clock, CheckCircle, XCircle, Loader2, AlertCircle, X } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useJobs, useCancelJob } from "@/lib/hooks";
import type { Job } from "@/lib/api";

const statusConfig = {
  queued: {
    icon: Clock,
    label: "In the crucible...",
    color: "text-muted-foreground",
    animate: false,
    badge: "queued" as const,
  },
  running: {
    icon: Loader2,
    label: "Transmuting...",
    color: "text-primary",
    animate: true,
    badge: "running" as const,
  },
  completed: {
    icon: CheckCircle,
    label: "Materialized ✨",
    color: "text-green-500",
    animate: false,
    badge: "completed" as const,
  },
  failed: {
    icon: XCircle,
    label: "Chaos won",
    color: "text-destructive",
    animate: false,
    badge: "failed" as const,
  },
  cancelled: {
    icon: X,
    label: "Aborted",
    color: "text-muted-foreground",
    animate: false,
    badge: "cancelled" as const,
  },
};

export function QueueMonitor() {
  const { data, isLoading, error } = useJobs({ limit: 10 });

  if (isLoading) {
    return <QueueMonitorSkeleton />;
  }

  if (error) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <AlertCircle className="h-8 w-8 mx-auto mb-2 text-destructive opacity-50" />
        <p className="text-sm terminal-text">Queue offline</p>
        <p className="text-xs">{error.message}</p>
      </div>
    );
  }

  const jobs = data?.jobs || [];

  return (
    <div className="space-y-3">
      {jobs.map((job) => (
        <QueueItem key={job.id} job={job} />
      ))}

      {jobs.length === 0 && (
        <div className="text-center py-8 text-muted-foreground">
          <Clock className="h-8 w-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm terminal-text">Queue empty</p>
          <p className="text-xs">The furnace awaits.</p>
        </div>
      )}
    </div>
  );
}

function QueueMonitorSkeleton() {
  return (
    <div className="space-y-3">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="p-3 rounded-md bg-secondary/30 space-y-2">
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-2 w-full" />
        </div>
      ))}
    </div>
  );
}

interface QueueItemProps {
  job: Job;
}

function QueueItem({ job }: QueueItemProps) {
  const cancelJob = useCancelJob();
  const config = statusConfig[job.status as keyof typeof statusConfig];
  const Icon = config?.icon || Clock;

  const canCancel = job.status === "queued" || job.status === "running";

  const handleCancel = () => {
    cancelJob.mutate(job.id);
  };

  return (
    <div className="p-3 rounded-md bg-secondary/30 space-y-2 group">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Icon
          className={cn(
            "h-4 w-4",
            config?.color,
            config?.animate && "animate-spin"
          )}
        />
        <span className="font-mono text-xs truncate flex-1">
          {job.id.slice(0, 8)}...
        </span>
        <Badge variant={config?.badge}>{job.status}</Badge>
        {canCancel && (
          <Button
            size="sm"
            variant="ghost"
            className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
            onClick={handleCancel}
            disabled={cancelJob.isPending}
          >
            <X className="h-3 w-3" />
          </Button>
        )}
      </div>

      {/* Progress */}
      {job.status === "running" && (
        <>
          <Progress value={job.progress * 100} className="h-1" />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span className="terminal-text">
              {job.current_node && `› ${job.current_node}`}
            </span>
            <span>{Math.round(job.progress * 100)}%</span>
          </div>
        </>
      )}

      {/* Error message */}
      {job.status === "failed" && job.error && (
        <p className="text-xs text-destructive truncate">{job.error}</p>
      )}

      {/* Status message */}
      {job.status !== "running" && job.status !== "failed" && (
        <p className="text-xs text-muted-foreground">{config?.label}</p>
      )}

      {/* Timing info for completed jobs */}
      {job.status === "completed" && job.gpu_seconds > 0 && (
        <p className="text-xs text-muted-foreground">
          ⚡ {job.gpu_seconds.toFixed(1)}s GPU • {job.cold_start_ms}ms cold start
        </p>
      )}
    </div>
  );
}
