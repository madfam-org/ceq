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

function getAuthHeaders(): HeadersInit {
  // In a real app, get this from auth context
  const token =
    typeof window !== "undefined" ? localStorage.getItem("janua_token") : null;
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
    `${API_BASE}/api/v1/workflows?${searchParams}`,
    {
      headers: getAuthHeaders(),
    }
  );
  return handleResponse(response);
}

export async function getWorkflow(id: string): Promise<Workflow> {
  const response = await fetch(`${API_BASE}/api/v1/workflows/${id}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

export async function createWorkflow(data: WorkflowCreate): Promise<Workflow> {
  const response = await fetch(`${API_BASE}/api/v1/workflows`, {
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
  const response = await fetch(`${API_BASE}/api/v1/workflows/${id}`, {
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
  const response = await fetch(`${API_BASE}/api/v1/workflows/${id}`, {
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

export async function runWorkflow(
  id: string,
  params: {
    input_params?: Record<string, unknown>;
    priority?: number;
    webhook_url?: string;
  }
): Promise<Job> {
  const response = await fetch(`${API_BASE}/api/v1/workflows/${id}/run`, {
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

  const response = await fetch(`${API_BASE}/api/v1/jobs?${searchParams}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

export async function getJob(id: string): Promise<Job> {
  const response = await fetch(`${API_BASE}/api/v1/jobs/${id}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

export async function pollJob(id: string): Promise<Job> {
  const response = await fetch(`${API_BASE}/api/v1/jobs/${id}/poll`, {
    headers: getAuthHeaders(),
  });
  return handleResponse(response);
}

export async function cancelJob(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/jobs/${id}`, {
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
  const response = await fetch(`${API_BASE}/api/v1/jobs/${id}/outputs`, {
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
  const ws = new WebSocket(`${wsUrl}/api/v1/jobs/${jobId}/stream`);

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

// Health check

export async function checkHealth(): Promise<{ status: string; message: string }> {
  const response = await fetch(`${API_BASE}/api/v1/health`);
  return handleResponse(response);
}
