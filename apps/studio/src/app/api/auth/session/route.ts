/**
 * Session Bootstrap API Route
 *
 * Returns the current Janua-backed Studio session from httpOnly cookies.
 */

import { NextRequest, NextResponse } from "next/server";
import { isJwtExpired, parseJwtUser } from "@/lib/jwt";
import {
  ACCESS_TOKEN_COOKIE,
  REFRESH_TOKEN_COOKIE,
  setSessionCookies,
  clearSessionCookies,
} from "@/lib/session-cookies";

const JANUA_URL = process.env.NEXT_PUBLIC_JANUA_URL || "https://auth.madfam.io";
const CLIENT_ID = process.env.NEXT_PUBLIC_JANUA_CLIENT_ID || "ceq-studio";
const CLIENT_SECRET = process.env.JANUA_CLIENT_SECRET || "";

function sessionJson(accessToken: string, request: NextRequest): NextResponse {
  const user = parseJwtUser(accessToken);

  if (!user) {
    const response = NextResponse.json(
      { error: "Invalid session token" },
      { status: 401 }
    );
    clearSessionCookies(response, request);
    return response;
  }

  return NextResponse.json(
    {
      access_token: accessToken,
      user,
      token_type: "Bearer",
    },
    {
      headers: {
        "Cache-Control": "no-store",
      },
    }
  );
}

async function refreshFromCookie(
  request: NextRequest,
  refreshToken: string
): Promise<NextResponse> {
  const tokenResponse = await fetch(`${JANUA_URL}/api/v1/oauth/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: refreshToken,
      client_id: CLIENT_ID,
      ...(CLIENT_SECRET && { client_secret: CLIENT_SECRET }),
    }),
  });

  if (!tokenResponse.ok) {
    const response = NextResponse.json(
      { error: "Session refresh failed" },
      { status: 401 }
    );
    clearSessionCookies(response, request);
    return response;
  }

  const tokens = await tokenResponse.json();
  const response = sessionJson(tokens.access_token, request);
  if (response.status < 400) {
    setSessionCookies(response, request, {
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token || refreshToken,
      expiresIn: tokens.expires_in,
    });
  }
  return response;
}

export async function GET(request: NextRequest) {
  const accessToken = request.cookies.get(ACCESS_TOKEN_COOKIE)?.value;
  const refreshToken = request.cookies.get(REFRESH_TOKEN_COOKIE)?.value;

  if (accessToken && !isJwtExpired(accessToken)) {
    return sessionJson(accessToken, request);
  }

  if (refreshToken) {
    return refreshFromCookie(request, refreshToken);
  }

  return NextResponse.json(
    { error: "No active Studio session" },
    {
      status: 401,
      headers: {
        "Cache-Control": "no-store",
      },
    }
  );
}
