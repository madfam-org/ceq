/**
 * CEQ API Client
 *
 * Type-safe API client for communicating with ceq-api.
 */

import { getSessionAuth, getToken, setAuth } from "@/lib/auth";

const API_BASE = "/api/proxy";
const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:5800";

// === Types ===

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  workflow_json: Record<string, unknown>;
  input_schema: Record<string, unknown>;
  tags: string[];
  is_public: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkflowCreate {
  name: string;
  description?: string;
  workflow_json: Record<string, unknown>;
  input_schema?: Record<string, unknown>;
  tags?: string[];
  is_public?: boolean;
}

export interface Job {
  id: string;
  workflow_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  current_node: string | null;
  error: string | null;
  input_params: Record<string, unknown>;
  outputs: Output[];
  output_metadata: Record<string, unknown>;
  queued_at: string;
  started_at: string | null;
  completed_at: string | null;
  gpu_seconds: number;
  cold_start_ms: number;
  worker_id: string | null;
  brand_message: string;
}

export interface Output {
  id: string;
  filename: string;
  storage_uri: string;
  public_url?: string | null;
  file_type: string;
  file_size_bytes: number;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  preview_url: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

// === Error Handling ===

export class APIError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail);
    this.name = "APIError";
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({
      detail: "Chaos in the signal. Retry? [↻]",
    }));
    throw new APIError(response.status, error.detail);
  }
  return response.json();
}

// === API Methods ===

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  return handleResponse<T>(response);
}

// Workflows

export async function getWorkflows(params?: {
  skip?: number;
  limit?: number;
  tag?: string;
  public_only?: boolean;
}): Promise<PaginatedResponse<Workflow>> {
  const searchParams = new URLSearchParams();
  if (params?.skip) searchParams.set("skip", String(params.skip));
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.tag) searchParams.set("tag", params.tag);
  if (params?.public_only) searchParams.set("public_only", "true");

  return apiFetch(`/v1/workflows/?${searchParams}`);
}

export async function getWorkflow(id: string): Promise<Workflow> {
  return apiFetch(`/v1/workflows/${id}`);
}

export async function createWorkflow(data: WorkflowCreate): Promise<Workflow> {
  return apiFetch("/v1/workflows", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });
}

export async function updateWorkflow(
  id: string,
  data: Partial<WorkflowCreate>
): Promise<Workflow> {
  return apiFetch(`/v1/workflows/${id}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });
}

export async function deleteWorkflow(id: string): Promise<void> {
  await apiFetch(`/v1/workflows/${id}`, {
    method: "DELETE",
  });
}

export interface WorkflowRunResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface WorkflowRunRequest {
  params?: Record<string, unknown>;
  priority?: number;
  webhook_url?: string;
}

export async function runWorkflow(
  id: string,
  data: WorkflowRunRequest = {}
): Promise<WorkflowRunResponse> {
  return apiFetch(`/v1/workflows/${id}/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });
}

// Jobs

export async function getJobs(params?: {
  skip?: number;
  limit?: number;
  status_filter?: string;
  workflow_id?: string;
}): Promise<{ jobs: Job[]; total: number; skip: number; limit: number }> {
  const searchParams = new URLSearchParams();
  if (params?.skip) searchParams.set("skip", String(params.skip));
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.status_filter) searchParams.set("status_filter", params.status_filter);
  if (params?.workflow_id) searchParams.set("workflow_id", params.workflow_id);

  return apiFetch(`/v1/jobs/?${searchParams}`);
}

export async function getJob(id: string): Promise<Job> {
  return apiFetch(`/v1/jobs/${id}`);
}

export async function pollJob(id: string): Promise<Job> {
  return apiFetch(`/v1/jobs/${id}/poll`);
}

export async function cancelJob(id: string): Promise<void> {
  await apiFetch(`/v1/jobs/${id}`, {
    method: "DELETE",
  });
}

export async function getJobOutputs(id: string): Promise<Output[]> {
  return apiFetch(`/v1/jobs/${id}/outputs`);
}

export async function getGalleryOutputs(params?: {
  skip?: number;
  limit?: number;
  file_type?: string;
}): Promise<{ outputs: Output[]; total: number }> {
  const searchParams = new URLSearchParams();
  if (params?.skip) searchParams.set("skip", String(params.skip));
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.file_type) searchParams.set("file_type", params.file_type);

  return apiFetch(`/v1/outputs/?${searchParams}`);
}

// WebSocket for real-time job updates

/** Resolve a Janua bearer token for job stream auth via session cookies. */
export async function resolveStreamAuthToken(): Promise<string | null> {
  const cached = getToken();
  if (cached) {
    return cached;
  }

  const session = await getSessionAuth();
  if (!session?.accessToken) {
    return null;
  }

  setAuth(session.accessToken, null, session.user);
  return session.accessToken;
}

export async function subscribeToJob(
  jobId: string,
  onMessage: (data: unknown) => void,
  onError?: (error: Event) => void,
  onClose?: () => void
): Promise<WebSocket> {
  const token = await resolveStreamAuthToken();
  const query = new URLSearchParams();
  if (token) {
    query.set("token", token);
  }

  const wsPath = `/v1/jobs/${jobId}/stream`;
  const wsUrl = query.size > 0 ? `${WS_BASE}${wsPath}?${query}` : `${WS_BASE}${wsPath}`;
  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch {
      console.error("Failed to parse WebSocket message");
    }
  };

  ws.onerror = (event) => {
    onError?.(event);
  };

  ws.onclose = () => {
    onClose?.();
  };

  return ws;
}

// Templates

export interface Template {
  id: string;
  name: string;
  description: string | null;
  category: "social" | "video" | "3d" | "utility";
  workflow_json: Record<string, unknown>;
  input_schema: Record<string, InputSchemaField>;
  tags: string[];
  thumbnail_url: string | null;
  preview_urls: string[];
  model_requirements: string[];
  vram_requirement_gb: number;
  fork_count: number;
  run_count: number;
  created_at: string;
  updated_at: string;
}

export interface InputSchemaField {
  type: "string" | "int" | "float" | "bool" | "image" | "select";
  label?: string;
  description?: string;
  default?: unknown;
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
  required?: boolean;
}

export async function getTemplates(params?: {
  skip?: number;
  limit?: number;
  category?: string;
  tag?: string;
}): Promise<{ templates: Template[]; total: number }> {
  const searchParams = new URLSearchParams();
  if (params?.skip) searchParams.set("skip", String(params.skip));
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.category) searchParams.set("category", params.category);
  if (params?.tag) searchParams.set("tag", params.tag);

  return apiFetch(`/v1/templates/?${searchParams}`);
}

export async function getTemplate(id: string): Promise<Template> {
  return apiFetch(`/v1/templates/${id}`);
}

export async function runTemplate(
  id: string,
  data: {
    params: Record<string, unknown>;
    priority?: number;
    webhook_url?: string;
  }
): Promise<WorkflowRunResponse> {
  return apiFetch(`/v1/templates/${id}/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });
}

export async function forkTemplate(id: string): Promise<Workflow> {
  return apiFetch(`/v1/templates/${id}/fork`, {
    method: "POST",
  });
}

// Health check

export async function checkHealth(): Promise<{ status: string; message: string }> {
  return apiFetch("/health");
}
