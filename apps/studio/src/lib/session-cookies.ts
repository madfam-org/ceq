import type { NextRequest, NextResponse } from "next/server";

export const ACCESS_TOKEN_COOKIE = "ceq_access_token";
export const REFRESH_TOKEN_COOKIE = "ceq_refresh_token";

const DEFAULT_ACCESS_MAX_AGE_SECONDS = 60 * 60;
const REFRESH_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

interface SessionCookieTokens {
  accessToken: string;
  refreshToken?: string | null;
  expiresIn?: number | null;
}

function isSecureRequest(request: NextRequest): boolean {
  const forwardedProto = request.headers.get("x-forwarded-proto");
  const host = request.headers.get("host") ?? "";
  return (
    forwardedProto === "https" ||
    request.nextUrl.protocol === "https:" ||
    host.endsWith(".ceq.lol") ||
    host === "ceq.lol"
  );
}

function accessMaxAge(expiresIn?: number | null): number {
  if (!expiresIn || !Number.isFinite(expiresIn)) {
    return DEFAULT_ACCESS_MAX_AGE_SECONDS;
  }
  return Math.max(60, Math.floor(expiresIn));
}

export function setSessionCookies(
  response: NextResponse,
  request: NextRequest,
  tokens: SessionCookieTokens
): void {
  const secure = isSecureRequest(request);

  response.cookies.set(ACCESS_TOKEN_COOKIE, tokens.accessToken, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: accessMaxAge(tokens.expiresIn),
  });

  if (tokens.refreshToken) {
    response.cookies.set(REFRESH_TOKEN_COOKIE, tokens.refreshToken, {
      httpOnly: true,
      sameSite: "lax",
      secure,
      path: "/",
      maxAge: REFRESH_MAX_AGE_SECONDS,
    });
  }
}

export function clearSessionCookies(
  response: NextResponse,
  request: NextRequest
): void {
  const secure = isSecureRequest(request);
  const options = {
    httpOnly: true,
    sameSite: "lax" as const,
    secure,
    path: "/",
    maxAge: 0,
  };

  response.cookies.set(ACCESS_TOKEN_COOKIE, "", options);
  response.cookies.set(REFRESH_TOKEN_COOKIE, "", options);
}
