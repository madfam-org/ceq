/**
 * Server-Mediated CEQ API Proxy
 *
 * All Studio API traffic is forwarded through this route so auth can be sourced
 * from httpOnly CEQ session cookies instead of browser-accessible storage.
 */

import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5800";

const FORWARDED_HEADERS = new Set([
  "accept",
  "accept-encoding",
  "accept-language",
  "authorization",
  "cache-control",
  "content-type",
  "dnt",
  "referer",
  "user-agent",
  "x-request-id",
  "x-forwarded-for",
  "x-forwarded-proto",
]);

const SUPPORTED_METHODS = new Set([
  "GET",
  "HEAD",
  "POST",
  "PUT",
  "PATCH",
  "DELETE",
]);

type HeadersLike = Headers & {
  getSetCookie?: () => string[];
};

function extractSetCookie(headers: HeadersLike): string[] {
  if (typeof headers.getSetCookie === "function") {
    return headers.getSetCookie();
  }
  const cookie = headers.get("set-cookie");
  return cookie ? [cookie] : [];
}

function resolveTargetPath(path: string[] = []): string {
  const tail = path.length > 0 ? `/${path.join("/")}` : "";
  return tail.startsWith("//") ? `/${tail.slice(2)}` : tail;
}

async function resolveSessionToken(
  request: NextRequest
): Promise<{ token: string | null; setCookie: string[] }> {
  const authHeader = request.headers.get("authorization");
  if (authHeader?.toLowerCase().startsWith("bearer ")) {
    return { token: authHeader.slice(7).trim(), setCookie: [] };
  }

  const cookieHeader = request.headers.get("cookie");
  if (!cookieHeader) {
    return { token: null, setCookie: [] };
  }

  try {
    const sessionResponse = await fetch(new URL("/api/auth/session", request.url), {
      method: "GET",
      headers: {
        cookie: cookieHeader,
        "cache-control": "no-store",
      },
    });

    if (!sessionResponse.ok) {
      const setCookie = extractSetCookie(sessionResponse.headers);
      return { token: null, setCookie };
    }

    const payload = await sessionResponse.json().catch(() => null);
    const token = typeof payload?.access_token === "string" ? payload.access_token : null;
    return { token, setCookie: extractSetCookie(sessionResponse.headers) };
  } catch {
    return { token: null, setCookie: [] };
  }

}

function forwardHeaders(request: NextRequest, token: string | null): Headers {
  const headers = new Headers();

  for (const [name, value] of request.headers) {
    const key = name.toLowerCase();
    if (FORWARDED_HEADERS.has(key)) {
      headers.set(name, value);
    }
  }

  if (!token && request.headers.has("authorization")) {
    headers.delete("authorization");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  return headers;
}

function cloneSessionCookies(
  response: NextResponse,
  setCookie: string[]
): void {
  for (const setCookieValue of setCookie) {
    response.headers.append("set-cookie", setCookieValue);
  }
}

async function proxy(
  request: NextRequest,
  context: { params: { path?: string[] } }
): Promise<NextResponse> {
  if (!SUPPORTED_METHODS.has(request.method)) {
    return NextResponse.json(
      { error: "Method not allowed" },
      { status: 405, headers: { Allow: Array.from(SUPPORTED_METHODS).join(", ") } }
    );
  }

  const targetPath = resolveTargetPath(context.params.path);
  const targetUrl = new URL(`${targetPath}${request.nextUrl.search}`, API_BASE);

  const { token, setCookie } = await resolveSessionToken(request);
  const headers = forwardHeaders(request, token);
  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  const upstream = await fetch(targetUrl.toString(), {
    method: request.method,
    headers,
    body,
  });

  const nextResponse = new NextResponse(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: upstream.headers,
  });

  cloneSessionCookies(nextResponse, setCookie);
  return nextResponse;
}

export async function GET(
  request: NextRequest,
  context: { params: { path?: string[] } }
): Promise<NextResponse> {
  return proxy(request, context);
}

export async function HEAD(
  request: NextRequest,
  context: { params: { path?: string[] } }
): Promise<NextResponse> {
  return proxy(request, context);
}

export async function POST(
  request: NextRequest,
  context: { params: { path?: string[] } }
): Promise<NextResponse> {
  return proxy(request, context);
}

export async function PUT(
  request: NextRequest,
  context: { params: { path?: string[] } }
): Promise<NextResponse> {
  return proxy(request, context);
}

export async function PATCH(
  request: NextRequest,
  context: { params: { path?: string[] } }
): Promise<NextResponse> {
  return proxy(request, context);
}

export async function DELETE(
  request: NextRequest,
  context: { params: { path?: string[] } }
): Promise<NextResponse> {
  return proxy(request, context);
}
