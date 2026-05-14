/**
 * Token Refresh API Route
 *
 * Refreshes expired access tokens using the refresh token.
 * Keeps client_secret server-side for security.
 */

import { NextRequest, NextResponse } from "next/server";
import {
  REFRESH_TOKEN_COOKIE,
  setSessionCookies,
  clearSessionCookies,
} from "@/lib/session-cookies";

const JANUA_URL = process.env.NEXT_PUBLIC_JANUA_URL || "https://auth.madfam.io";
const CLIENT_ID = process.env.NEXT_PUBLIC_JANUA_CLIENT_ID || "ceq-studio";
const CLIENT_SECRET = process.env.JANUA_CLIENT_SECRET || "";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));
    const refresh_token =
      body.refresh_token || request.cookies.get(REFRESH_TOKEN_COOKIE)?.value;

    if (!refresh_token) {
      return NextResponse.json(
        { error: "Refresh token required" },
        { status: 400 }
      );
    }

    // Refresh tokens with Janua
    const tokenResponse = await fetch(`${JANUA_URL}/api/v1/oauth/token`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        refresh_token,
        client_id: CLIENT_ID,
        ...(CLIENT_SECRET && { client_secret: CLIENT_SECRET }),
      }),
    });

    if (!tokenResponse.ok) {
      const error = await tokenResponse.text();
      console.error("Token refresh failed:", error);
      const response = NextResponse.json(
        { error: "Token refresh failed" },
        { status: tokenResponse.status }
      );
      clearSessionCookies(response, request);
      return response;
    }

    const tokens = await tokenResponse.json();

    const response = NextResponse.json({
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token,
      expires_in: tokens.expires_in,
      token_type: tokens.token_type || "Bearer",
    });
    setSessionCookies(response, request, {
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token || refresh_token,
      expiresIn: tokens.expires_in,
    });
    return response;
  } catch (error) {
    console.error("Token refresh error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
