/**
 * CEQ API Client
 *
 * Type-safe API client for communicating with ceq-api.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5800";

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

import { getToken } from "@/lib/auth";

function getAuthHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
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

  const response = await fetch(
    `${API_BASE}/v1/workflows/?${searchParams}`,
    {
      headers: getAuthHeaders(),
    }
  );
  return handleResponse(response);
}

export async function getWorkflow(id: string): Promise<Workflow> {
  const response = await fetch(`${API_BASE}/v1/workflows/${id}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

export async function createWorkflow(data: WorkflowCreate): Promise<Workflow> {
  const response = await fetch(`${API_BASE}/v1/workflows`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

export async function updateWorkflow(
  id: string,
  data: Partial<WorkflowCreate>
): Promise<Workflow> {
  const response = await fetch(`${API_BASE}/v1/workflows/${id}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

export async function deleteWorkflow(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/v1/workflows/${id}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({
      detail: "Failed to delete workflow",
    }));
    throw new APIError(response.status, error.detail);
  }
}

export interface WorkflowRunResponse {
  job_id: string;
  status: string;
  message: string;
}

export async function runWorkflow(
  id: string,
  params: {
    input_params?: Record<string, unknown>;
    priority?: number;
    webhook_url?: string;
  }
): Promise<WorkflowRunResponse> {
  const response = await fetch(`${API_BASE}/v1/workflows/${id}/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(params),
  });
  return handleResponse(response);
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

  const response = await fetch(`${API_BASE}/v1/jobs/?${searchParams}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

export async function getJob(id: string): Promise<Job> {
  const response = await fetch(`${API_BASE}/v1/jobs/${id}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

export async function pollJob(id: string): Promise<Job> {
  const response = await fetch(`${API_BASE}/v1/jobs/${id}/poll`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

export async function cancelJob(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/v1/jobs/${id}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({
      detail: "Failed to cancel job",
    }));
    throw new APIError(response.status, error.detail);
  }
}

export async function getJobOutputs(id: string): Promise<Output[]> {
  const response = await fetch(`${API_BASE}/v1/jobs/${id}/outputs`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
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

  const response = await fetch(`${API_BASE}/v1/outputs/?${searchParams}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

// WebSocket for real-time job updates

export function subscribeToJob(
  jobId: string,
  onMessage: (data: unknown) => void,
  onError?: (error: Event) => void,
  onClose?: () => void
): WebSocket {
  const wsUrl = API_BASE.replace(/^http/, "ws");
  const ws = new WebSocket(`${wsUrl}/v1/jobs/${jobId}/stream`);

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

  const response = await fetch(`${API_BASE}/v1/templates/?${searchParams}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

export async function getTemplate(id: string): Promise<Template> {
  const response = await fetch(`${API_BASE}/v1/templates/${id}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

export async function runTemplate(
  id: string,
  params: {
    input_params: Record<string, unknown>;
    priority?: number;
  }
): Promise<WorkflowRunResponse> {
  const response = await fetch(`${API_BASE}/v1/templates/${id}/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(params),
  });
  return handleResponse(response);
}

export async function forkTemplate(id: string): Promise<Workflow> {
  const response = await fetch(`${API_BASE}/v1/templates/${id}/fork`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

// Health check

export async function checkHealth(): Promise<{ status: string; message: string }> {
  const response = await fetch(`${API_BASE}/health`);
  return handleResponse(response);
}
