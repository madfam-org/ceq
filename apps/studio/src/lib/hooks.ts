"use client";

/**
 * CEQ React Query Hooks
 *
 * Type-safe hooks for data fetching and mutations.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import * as api from "./api";

// === Query Keys ===

export const queryKeys = {
  workflows: ["workflows"] as const,
  workflow: (id: string) => ["workflows", id] as const,
  jobs: ["jobs"] as const,
  job: (id: string) => ["jobs", id] as const,
  jobOutputs: (id: string) => ["jobs", id, "outputs"] as const,
  health: ["health"] as const,
};

// === Workflow Hooks ===

export function useWorkflows(params?: Parameters<typeof api.getWorkflows>[0]) {
  return useQuery({
    queryKey: [...queryKeys.workflows, params],
    queryFn: () => api.getWorkflows(params),
  });
}

export function useWorkflow(id: string) {
  return useQuery({
    queryKey: queryKeys.workflow(id),
    queryFn: () => api.getWorkflow(id),
    enabled: !!id,
  });
}

export function useCreateWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.createWorkflow,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.workflows });
      toast.success("Workflow materialized. ✨");
    },
    onError: (error) => {
      toast.error(error instanceof api.APIError ? error.detail : "Chaos won this round.");
    },
  });
}

export function useUpdateWorkflow(id: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: Parameters<typeof api.updateWorkflow>[1]) =>
      api.updateWorkflow(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.workflow(id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.workflows });
      toast.success("Entropy reconfigured.");
    },
    onError: (error) => {
      toast.error(error instanceof api.APIError ? error.detail : "Signal disrupted.");
    },
  });
}

export function useDeleteWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.deleteWorkflow,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.workflows });
      toast.success("Entropy released.");
    },
    onError: (error) => {
      toast.error(error instanceof api.APIError ? error.detail : "Could not release entropy.");
    },
  });
}

export function useRunWorkflow(workflowId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: Parameters<typeof api.runWorkflow>[1]) =>
      api.runWorkflow(workflowId, params),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
      toast.success(`Job queued. ID: ${result.job_id.slice(0, 8)}...`);
    },
    onError: (error) => {
      toast.error(
        error instanceof api.APIError ? error.detail : "Failed to ignite the furnace."
      );
    },
  });
}

// === Job Hooks ===

export function useJobs(params?: Parameters<typeof api.getJobs>[0]) {
  return useQuery({
    queryKey: [...queryKeys.jobs, params],
    queryFn: () => api.getJobs(params),
    refetchInterval: 5000, // Poll every 5 seconds
  });
}

export function useJob(id: string) {
  return useQuery({
    queryKey: queryKeys.job(id),
    queryFn: () => api.getJob(id),
    enabled: !!id,
    refetchInterval: (query) => {
      // Stop polling when job is complete
      const job = query.state.data;
      if (
        job?.status === "completed" ||
        job?.status === "failed" ||
        job?.status === "cancelled"
      ) {
        return false;
      }
      return 2000; // Poll every 2 seconds while running
    },
  });
}

export function usePollJob(id: string) {
  return useQuery({
    queryKey: [...queryKeys.job(id), "poll"],
    queryFn: () => api.pollJob(id),
    enabled: !!id,
    refetchInterval: 1000, // Fast polling from Redis
  });
}

export function useCancelJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.cancelJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
      toast.success("Transmutation aborted.");
    },
    onError: (error) => {
      toast.error(
        error instanceof api.APIError ? error.detail : "Could not halt the furnace."
      );
    },
  });
}

export function useJobOutputs(id: string) {
  return useQuery({
    queryKey: queryKeys.jobOutputs(id),
    queryFn: () => api.getJobOutputs(id),
    enabled: !!id,
  });
}

// === Health Hook ===

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: api.checkHealth,
    retry: false,
    refetchInterval: 30000, // Check health every 30 seconds
  });
}
