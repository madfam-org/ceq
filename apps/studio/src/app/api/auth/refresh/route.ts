/**
 * Token Refresh API Route
 *
 * Refreshes expired access tokens using the refresh token.
 * Keeps client_secret server-side for security.
 */

import { NextRequest, NextResponse } from "next/server";

const JANUA_URL = process.env.NEXT_PUBLIC_JANUA_URL || "https://auth.madfam.io";
const CLIENT_ID = process.env.NEXT_PUBLIC_JANUA_CLIENT_ID || "ceq-studio";
const CLIENT_SECRET = process.env.JANUA_CLIENT_SECRET || "";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { refresh_token } = body;

    if (!refresh_token) {
      return NextResponse.json(
        { error: "Refresh token required" },
        { status: 400 }
      );
    }

    // Refresh tokens with Janua
    const tokenResponse = await fetch(`${JANUA_URL}/api/v1/auth/token`, {
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
      return NextResponse.json(
        { error: "Token refresh failed" },
        { status: tokenResponse.status }
      );
    }

    const tokens = await tokenResponse.json();

    return NextResponse.json({
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token,
      expires_in: tokens.expires_in,
      token_type: tokens.token_type || "Bearer",
    });
  } catch (error) {
    console.error("Token refresh error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
