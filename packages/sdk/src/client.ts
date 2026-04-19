import {
  CardData,
  CeqApiError,
  RenderRequest,
  RenderResponse,
  TemplateInfo,
} from "./types.js";

export interface CeqClientOptions {
  /**
   * Base URL of the CEQ API. Defaults to https://api.ceq.lol.
   * Override for staging or local dev (e.g. http://localhost:5800).
   */
  baseUrl?: string;

  /**
   * Janua bearer token, or a function returning one (async OK).
   * Function form is preferred in long-running processes so the SDK can
   * pick up refreshed tokens without being reconstructed.
   */
  token?: string | (() => string | Promise<string>);

  /**
   * Custom fetch implementation. Defaults to globalThis.fetch.
   * Useful in environments without a global fetch (old Node) or for
   * wrapping with tracing/retry.
   */
  fetch?: typeof fetch;

  /** Per-request timeout in milliseconds. Default 30_000. */
  timeoutMs?: number;
}

const DEFAULT_BASE_URL = "https://api.ceq.lol";
const DEFAULT_TIMEOUT_MS = 30_000;

/**
 * Client for the CEQ asset-generation API.
 *
 * ```ts
 * const ceq = new CeqClient({ token: juanaAccessToken });
 * const { url } = await ceq.renderCard({
 *   title: "Volcán",
 *   subtitle: "Elemental / Fire",
 *   accent: "#FF5A3C",
 *   badge: "SR",
 * });
 * // persist `url` on your card record — it's immutable.
 * ```
 */
export class CeqClient {
  private readonly baseUrl: string;
  private readonly tokenSource: CeqClientOptions["token"];
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;

  constructor(options: CeqClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.tokenSource = options.token;
    this.fetchImpl = options.fetch ?? globalThis.fetch;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

    if (!this.fetchImpl) {
      throw new Error(
        "ceq sdk: no fetch implementation available. Pass `fetch` in options or run on a platform with globalThis.fetch."
      );
    }
  }

  /**
   * Render a card thumbnail. Deterministic: identical inputs return the same URL.
   * Safe to call on every record save — cache lookups are cheap.
   */
  async renderCard(
    data: CardData,
    opts: { template?: string } = {}
  ): Promise<RenderResponse> {
    return this.post<RenderResponse>("/v1/render/card", {
      template: opts.template ?? "card-standard",
      data: data as unknown as Record<string, unknown>,
    });
  }

  /**
   * Render a generic thumbnail. You must supply `template` — see listTemplates().
   */
  async renderThumbnail<TData extends Record<string, unknown>>(
    request: RenderRequest<TData>
  ): Promise<RenderResponse> {
    return this.post<RenderResponse>("/v1/render/thumbnail", request);
  }

  /** List available render templates. */
  async listTemplates(): Promise<TemplateInfo[]> {
    return this.get<TemplateInfo[]>("/v1/render/templates");
  }

  // ---------- low-level ----------

  private async resolveToken(): Promise<string | undefined> {
    if (!this.tokenSource) return undefined;
    if (typeof this.tokenSource === "function") {
      return await this.tokenSource();
    }
    return this.tokenSource;
  }

  private async headers(): Promise<Record<string, string>> {
    const token = await this.resolveToken();
    const headers: Record<string, string> = {
      "content-type": "application/json",
      accept: "application/json",
    };
    if (token) {
      headers.authorization = `Bearer ${token}`;
    }
    return headers;
  }

  private async request<T>(path: string, init: RequestInit): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...init,
        headers: {
          ...(await this.headers()),
          ...(init.headers as Record<string, string> | undefined),
        },
        signal: controller.signal,
      });

      if (!response.ok) {
        let detail = response.statusText;
        try {
          const body = (await response.json()) as { detail?: string };
          if (body && typeof body.detail === "string") detail = body.detail;
        } catch {
          // non-JSON body; keep statusText
        }
        throw new CeqApiError(response.status, detail, response);
      }

      if (response.status === 204) return undefined as T;
      return (await response.json()) as T;
    } finally {
      clearTimeout(timer);
    }
  }

  private async get<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: "GET" });
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }
}
