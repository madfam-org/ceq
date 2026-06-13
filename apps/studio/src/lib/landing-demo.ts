const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://api.ceq.lol";
const APP_BASE = process.env.NEXT_PUBLIC_APP_URL || "https://app.ceq.lol";

/** Post-login path for visitors who engaged with the landing demo. */
export const DEMO_SIGNUP_RETURN_TO = "/templates?onboarding=demo";

export type DemoPresetId = "card" | "thumbnail" | "audio" | "plate";

export interface DemoPresetInfo {
  id: DemoPresetId;
  label: string;
  title: string;
  api_path: string;
  credit_cost: number;
  input_summary: string;
  output_summary: string;
}

export interface DemoRenderResult {
  url: string;
  storage_uri: string;
  hash: string;
  template: string;
  template_version: string;
  content_type: string;
  cached: boolean;
}

export interface DemoStatus {
  api: string;
  demo_enabled: boolean;
  workflow_templates: number;
  render_templates: number;
  render_template_names: string[];
}

export interface WorkflowTemplateSummary {
  id: string;
  name: string;
  description: string | null;
  category: string;
  tags: string[];
  thumbnail_url: string | null;
  run_count: number;
}

export type LandingEventProperties = Record<string, boolean | number | string>;

interface DataLayerWindow extends Window {
  dataLayer?: Array<Record<string, unknown>>;
}

export function trackLandingEvent(
  event: string,
  properties: LandingEventProperties = {},
): void {
  if (typeof window === "undefined") return;

  const detail = {
    event,
    properties,
    timestamp: new Date().toISOString(),
  };

  window.dispatchEvent(new CustomEvent("ceq:landing-event", { detail }));
  (window as DataLayerWindow).dataLayer?.push({
    event: `ceq_${event}`,
    ...properties,
  });
}

export function isAppHost(): boolean {
  if (typeof window === "undefined") return false;
  const host = window.location.host;
  return host.startsWith("app.") || host === "localhost" || host.startsWith("localhost:");
}

export function startSignIn(
  returnTo: string,
  login: (path: string) => void,
): void {
  if (isAppHost()) {
    login(returnTo);
    return;
  }
  if (typeof window !== "undefined") {
    const url = new URL("/login", APP_BASE);
    url.searchParams.set("returnTo", returnTo);
    window.location.href = url.toString();
  }
}

export async function fetchDemoStatus(): Promise<DemoStatus | null> {
  try {
    const res = await fetch(`${API_BASE}/v1/demo/status`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as DemoStatus;
  } catch {
    return null;
  }
}

export async function fetchDemoPresets(): Promise<DemoPresetInfo[]> {
  const res = await fetch(`${API_BASE}/v1/demo/presets`);
  if (!res.ok) {
    throw new Error(`Failed to load demo presets (${res.status})`);
  }
  return (await res.json()) as DemoPresetInfo[];
}

export async function runDemoRender(presetId: DemoPresetId): Promise<DemoRenderResult> {
  const res = await fetch(`${API_BASE}/v1/demo/render/${presetId}`, {
    method: "POST",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "Render failed" }));
    throw new Error(typeof body.detail === "string" ? body.detail : "Render failed");
  }
  return (await res.json()) as DemoRenderResult;
}

export async function fetchPublicTemplates(limit = 6): Promise<WorkflowTemplateSummary[]> {
  const res = await fetch(`${API_BASE}/v1/templates/?limit=${limit}`);
  if (!res.ok) {
    throw new Error(`Failed to load templates (${res.status})`);
  }
  const body = (await res.json()) as { templates: WorkflowTemplateSummary[] };
  return body.templates;
}

export { API_BASE, APP_BASE };
