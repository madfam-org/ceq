/**
 * Token Exchange API Route
 *
 * Exchanges authorization code for tokens with Janua.
 * Keeps client_secret server-side for security.
 */

import { NextRequest, NextResponse } from "next/server";

const JANUA_URL = process.env.NEXT_PUBLIC_JANUA_URL || "https://auth.madfam.io";
const CLIENT_ID = process.env.NEXT_PUBLIC_JANUA_CLIENT_ID || "ceq-studio";
const CLIENT_SECRET = process.env.JANUA_CLIENT_SECRET || "";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { code } = body;

    if (!code) {
      return NextResponse.json(
        { error: "Authorization code required" },
        { status: 400 }
      );
    }

    // Get the redirect URI from the request origin
    const origin = request.headers.get("origin") || request.nextUrl.origin;
    const redirectUri = `${origin}/auth/callback`;

    // Exchange code for tokens with Janua
    const tokenResponse = await fetch(`${JANUA_URL}/api/v1/auth/token`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        code,
        redirect_uri: redirectUri,
        client_id: CLIENT_ID,
        ...(CLIENT_SECRET && { client_secret: CLIENT_SECRET }),
      }),
    });

    if (!tokenResponse.ok) {
      const error = await tokenResponse.text();
      console.error("Token exchange failed:", error);
      return NextResponse.json(
        { error: "Token exchange failed" },
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
    console.error("Token exchange error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
