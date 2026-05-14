/**
 * Logout API Route
 *
 * Clears CEQ Studio session cookies before the browser leaves for Janua logout.
 */

import { NextRequest, NextResponse } from "next/server";
import { clearSessionCookies } from "@/lib/session-cookies";

export async function POST(request: NextRequest) {
  const response = NextResponse.json(
    { ok: true },
    {
      headers: {
        "Cache-Control": "no-store",
      },
    }
  );
  clearSessionCookies(response, request);
  return response;
}
