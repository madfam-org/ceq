import { describe, expect, it, vi } from "vitest";
import { CeqApiError, CeqClient } from "./index.js";

function mockFetch(
  responses: Array<{ status: number; body?: unknown }>
): typeof fetch {
  let idx = 0;
  return vi.fn(async () => {
    const r = responses[idx++];
    if (!r) throw new Error("no more mocked responses");
    return new Response(r.body === undefined ? null : JSON.stringify(r.body), {
      status: r.status,
      headers: { "content-type": "application/json" },
    });
  }) as unknown as typeof fetch;
}

describe("CeqClient", () => {
  it("renderCard posts to /v1/render/card with the card-standard template", async () => {
    const fetchImpl = mockFetch([
      {
        status: 200,
        body: {
          url: "https://cdn.ceq.lol/render/card-standard/abc.png",
          storage_uri: "r2://ceq-assets/render/card-standard/abc.png",
          hash: "abc",
          template: "card-standard",
          template_version: "1",
          content_type: "image/png",
          cached: false,
        },
      },
    ]);
    const ceq = new CeqClient({ fetch: fetchImpl, token: "t" });

    const result = await ceq.renderCard({
      title: "Volcán",
      accent: "#FF5A3C",
    });

    expect(result.url).toContain("cdn.ceq.lol");
    expect(result.template).toBe("card-standard");
    expect(fetchImpl).toHaveBeenCalledOnce();
    const call = (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0]!;
    expect(call[0]).toBe("https://api.ceq.lol/v1/render/card");
    const init = call[1] as RequestInit;
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string);
    expect(body.template).toBe("card-standard");
    expect(body.data.title).toBe("Volcán");
    const headers = init.headers as Record<string, string>;
    expect(headers.authorization).toBe("Bearer t");
  });

  it("throws CeqApiError with detail on non-2xx", async () => {
    const fetchImpl = mockFetch([
      { status: 404, body: { detail: "unknown template: 'nope'" } },
    ]);
    const ceq = new CeqClient({ fetch: fetchImpl });

    await expect(
      ceq.renderThumbnail({ template: "nope", data: { title: "x" } })
    ).rejects.toMatchObject({
      name: "CeqApiError",
      status: 404,
      detail: "unknown template: 'nope'",
    });
  });

  it("resolves a token function at request time", async () => {
    let calls = 0;
    const tokenFn = async () => {
      calls += 1;
      return `token-${calls}`;
    };
    const fetchImpl = mockFetch([
      { status: 200, body: [] },
      { status: 200, body: [] },
    ]);
    const ceq = new CeqClient({ fetch: fetchImpl, token: tokenFn });

    await ceq.listTemplates();
    await ceq.listTemplates();

    const mockFn = fetchImpl as unknown as ReturnType<typeof vi.fn>;
    const h1 = (mockFn.mock.calls[0]![1] as RequestInit).headers as Record<
      string,
      string
    >;
    const h2 = (mockFn.mock.calls[1]![1] as RequestInit).headers as Record<
      string,
      string
    >;
    expect(h1.authorization).toBe("Bearer token-1");
    expect(h2.authorization).toBe("Bearer token-2");
  });

  it("uses the provided baseUrl", async () => {
    const fetchImpl = mockFetch([{ status: 200, body: [] }]);
    const ceq = new CeqClient({
      fetch: fetchImpl,
      baseUrl: "http://localhost:5800/",
    });
    await ceq.listTemplates();
    const mockFn = fetchImpl as unknown as ReturnType<typeof vi.fn>;
    expect(mockFn.mock.calls[0]![0]).toBe(
      "http://localhost:5800/v1/render/templates"
    );
  });

  it("aborts on timeout", async () => {
    const slowFetch: typeof fetch = vi.fn(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError"))
          );
        })
    ) as unknown as typeof fetch;

    const ceq = new CeqClient({ fetch: slowFetch, timeoutMs: 10 });
    await expect(ceq.listTemplates()).rejects.toThrow();
  });

  it("does not send authorization header when no token configured", async () => {
    const fetchImpl = mockFetch([{ status: 200, body: [] }]);
    const ceq = new CeqClient({ fetch: fetchImpl });
    await ceq.listTemplates();
    const mockFn = fetchImpl as unknown as ReturnType<typeof vi.fn>;
    const headers = (mockFn.mock.calls[0]![1] as RequestInit)
      .headers as Record<string, string>;
    expect(headers.authorization).toBeUndefined();
  });
});

describe("CeqApiError", () => {
  it("carries status + detail + response", () => {
    const err = new CeqApiError(500, "boom");
    expect(err.status).toBe(500);
    expect(err.detail).toBe("boom");
    expect(err.message).toContain("500");
    expect(err.message).toContain("boom");
  });

  it("falls back to statusText when the error body is not JSON", async () => {
    // Non-JSON body (e.g. HTML 502 page, plaintext gateway error).
    // The SDK's body.json() call throws; detail should fall back to statusText.
    const fetchImpl: typeof fetch = vi.fn(async () =>
      new Response("<html>bad gateway</html>", {
        status: 502,
        statusText: "Bad Gateway",
        headers: { "content-type": "text/html" },
      })
    ) as unknown as typeof fetch;

    const ceq = new CeqClient({ fetch: fetchImpl });
    await expect(ceq.listTemplates()).rejects.toMatchObject({
      name: "CeqApiError",
      status: 502,
      detail: "Bad Gateway",
    });
  });
});
