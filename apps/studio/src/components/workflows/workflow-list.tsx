"use client";

import { Workflow, Play, MoreHorizontal, Clock, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useWorkflows, useRunWorkflow, useDeleteWorkflow } from "@/lib/hooks";
import type { Workflow as WorkflowType } from "@/lib/api";

export function WorkflowList() {
  const { data, isLoading, error } = useWorkflows({ limit: 10 });

  if (isLoading) {
    return <WorkflowListSkeleton />;
  }

  if (error) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <AlertCircle className="h-12 w-12 mx-auto mb-4 text-destructive opacity-50" />
        <p className="terminal-text">Signal lost in the noise.</p>
        <p className="text-sm">{error.message}</p>
      </div>
    );
  }

  // API returns { workflows: [...] }, not { items: [...] }
  const workflows = (data as { workflows?: WorkflowType[] })?.workflows || [];

  return (
    <div className="space-y-2">
      {workflows.map((workflow) => (
        <WorkflowItem key={workflow.id} workflow={workflow} />
      ))}

      {workflows.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <Workflow className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p className="terminal-text">No workflows yet.</p>
          <p className="text-sm">Create one to start quantizing entropy.</p>
        </div>
      )}
    </div>
  );
}

function WorkflowListSkeleton() {
  return (
    <div className="space-y-2">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="flex items-center gap-4 p-3 rounded-md bg-secondary/50">
          <Skeleton className="h-10 w-10 rounded-md" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );
}

interface WorkflowItemProps {
  workflow: WorkflowType;
}

function WorkflowItem({ workflow }: WorkflowItemProps) {
  const runWorkflow = useRunWorkflow(workflow.id);
  const deleteWorkflow = useDeleteWorkflow();

  const handleRun = () => {
    runWorkflow.mutate({});
  };

  const handleDelete = () => {
    if (confirm("Release this entropy back to chaos?")) {
      deleteWorkflow.mutate(workflow.id);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now.getTime() - date.getTime();

    const minutes = Math.floor(diff / 60000);
    if (minutes < 60) return `${minutes}m ago`;

    const hours = Math.floor(diff / 3600000);
    if (hours < 24) return `${hours}h ago`;

    const days = Math.floor(diff / 86400000);
    return `${days}d ago`;
  };

  return (
    <div className="group flex items-center gap-4 p-3 rounded-md bg-secondary/50 hover:bg-secondary transition-colors">
      {/* Icon */}
      <div className="flex-shrink-0 h-10 w-10 rounded-md bg-primary/10 flex items-center justify-center">
        <Workflow className="h-5 w-5 text-primary" />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="font-mono text-sm font-medium truncate">
            {workflow.name}
          </h3>
          {workflow.is_public && (
            <Badge variant="secondary" className="text-xs">
              public
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground truncate">
          {workflow.description || "No description"}
        </p>
      </div>

      {/* Tags */}
      {workflow.tags && workflow.tags.length > 0 && (
        <div className="hidden md:flex items-center gap-1">
          {workflow.tags.slice(0, 2).map((tag) => (
            <Badge key={tag} variant="outline" className="text-xs">
              {tag}
            </Badge>
          ))}
        </div>
      )}

      {/* Last run */}
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        <Clock className="h-3 w-3" />
        <span>{formatDate(workflow.updated_at)}</span>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <Button
          size="sm"
          variant="ghost"
          className="h-8 w-8 p-0"
          title="Run workflow"
          onClick={handleRun}
          disabled={runWorkflow.isPending}
        >
          <Play className="h-4 w-4" />
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="ghost" className="h-8 w-8 p-0">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem>Edit</DropdownMenuItem>
            <DropdownMenuItem>Duplicate</DropdownMenuItem>
            <DropdownMenuItem>Export</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="text-destructive"
              onClick={handleDelete}
            >
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
