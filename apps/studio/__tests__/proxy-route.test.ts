import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { DELETE, GET, POST } from "@/app/api/proxy/[[...path]]/route";

const mockFetch = vi.fn();
global.fetch = mockFetch;

function headersToMap(headers: Headers): Record<string, string> {
  const out: Record<string, string> = {};
  headers.forEach((value, key) => {
    out[key] = value;
  });
  return out;
}

function requestFor(path: string, init: RequestInit = {}): NextRequest {
  return new NextRequest(`https://app.ceq.lol/api/proxy${path}`, {
    method: init.method,
    headers: init.headers,
    body: init.body,
  });
}

describe("Studio API proxy route", () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  it("forwards methods and headers, injecting Authorization from session cookie", async () => {
    const responseHeaders = new Headers();
    responseHeaders.set("content-type", "application/json");

    const sessionBody = { access_token: "session-token" };
    mockFetch
      .mockResolvedValueOnce(
        new Response(JSON.stringify(sessionBody), {
          status: 200,
          headers: {
            "set-cookie": "ceq_access_token=rotated; HttpOnly; Path=/; Max-Age=3600",
          },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ job_id: "job-1" }), {
          status: 201,
          headers: responseHeaders,
        }),
      );

    const request = requestFor("/v1/jobs", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        cookie: "ceq_refresh_token=refresh-token",
      },
      body: JSON.stringify({ prompt: "entropy" }),
    });

    const response = await POST(request, { params: { path: ["v1", "jobs"] } });
    const body = await response.json();

    expect(response.status).toBe(201);
    expect(body).toEqual({ job_id: "job-1" });

    const [sessionCallUrl, sessionInit] = mockFetch.mock.calls[0];
    expect(sessionCallUrl.toString()).toBe("https://app.ceq.lol/api/auth/session");
    expect(sessionInit?.headers).toMatchObject({
      cookie: "ceq_refresh_token=refresh-token",
      "cache-control": "no-store",
    });

    const [upstreamCallUrl, upstreamInit] = mockFetch.mock.calls[1];
    expect(upstreamCallUrl).toBe("http://localhost:5800/v1/jobs");
    const upstreamHeaders = headersToMap(upstreamInit.headers as Headers);
    expect(upstreamHeaders).toMatchObject({
      authorization: "Bearer session-token",
      "content-type": "application/json",
    });
    expect(upstreamHeaders.cookie).toBeUndefined();
    expect(await response.headers.get("set-cookie")).toBe(
      "ceq_access_token=rotated; HttpOnly; Path=/; Max-Age=3600"
    );
  });

  it("passes through upstream request headers for forwarded methods", async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(null, { status: 401, headers: { "x-upstream": "missing-auth" } }),
    );

    const request = requestFor("/v1/jobs/job-1", {
      method: "GET",
      headers: {
        accept: "application/json",
        authorization: "Bearer direct",
      },
    });

    const response = await GET(request, { params: { path: ["v1", "jobs", "job-1"] } });

    expect(response.status).toBe(401);
    const [upstreamCallUrl, upstreamInit] = mockFetch.mock.calls[0];
    expect(upstreamCallUrl).toBe("http://localhost:5800/v1/jobs/job-1");
    const upstreamHeaders = headersToMap(upstreamInit.headers as Headers);
    expect(upstreamHeaders).toMatchObject({
      accept: "application/json",
      authorization: "Bearer direct",
    });
    expect(response.headers.get("x-upstream")).toBe("missing-auth");
  });

  it("supports DELETE", async () => {
    mockFetch.mockResolvedValueOnce(new Response(null, { status: 204 }));

    const request = requestFor("/v1/jobs/job-1", { method: "DELETE" });
    const response = await DELETE(request, { params: { path: ["v1", "jobs", "job-1"] } });
    expect(response.status).toBe(204);

    const [upstreamCallUrl, upstreamInit] = mockFetch.mock.calls[0];
    expect(upstreamCallUrl).toBe("http://localhost:5800/v1/jobs/job-1");
    expect(upstreamInit.method).toBe("DELETE");
  });
});
