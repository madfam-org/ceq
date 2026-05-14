import { describe, expect, it } from "vitest";
import type { NextRequest } from "next/server";
import {
  buildLoginRedirect,
  hasUsableSessionCookie,
  isAppHost,
  isPublicAppPath,
} from "../src/middleware";
import {
  ACCESS_TOKEN_COOKIE,
  REFRESH_TOKEN_COOKIE,
} from "@/lib/session-cookies";

function base64Url(value: object): string {
  return btoa(JSON.stringify(value))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function createJwt(payload: object): string {
  return `${base64Url({ alg: "none", typ: "JWT" })}.${base64Url(payload)}.sig`;
}

function requestWithCookies(cookies: Record<string, string>): NextRequest {
  return {
    cookies: {
      get: (name: string) =>
        cookies[name] ? { name, value: cookies[name] } : undefined,
    },
  } as unknown as NextRequest;
}

describe("Studio middleware helpers", () => {
  it("splits app hostnames from marketing hostnames", () => {
    expect(isAppHost("app.ceq.lol")).toBe(true);
    expect(isAppHost("app.preview.ceq.lol")).toBe(true);
    expect(isAppHost("localhost")).toBe(true);
    expect(isAppHost("ceq.lol")).toBe(false);
  });

  it("keeps login and auth endpoints public on the app host", () => {
    expect(isPublicAppPath("/login")).toBe(true);
    expect(isPublicAppPath("/login/reset")).toBe(true);
    expect(isPublicAppPath("/auth/callback")).toBe(true);
    expect(isPublicAppPath("/api/auth/session")).toBe(true);
    expect(isPublicAppPath("/workflows")).toBe(false);
  });

  it("accepts either a valid access token or a refresh cookie", () => {
    const validAccessToken = createJwt({
      sub: "user-1",
      email: "ada@example.com",
      exp: Math.floor(Date.now() / 1000) + 3600,
    });
    const expiredAccessToken = createJwt({
      sub: "user-1",
      email: "ada@example.com",
      exp: Math.floor(Date.now() / 1000) - 3600,
    });

    expect(
      hasUsableSessionCookie(
        requestWithCookies({ [ACCESS_TOKEN_COOKIE]: validAccessToken })
      )
    ).toBe(true);
    expect(
      hasUsableSessionCookie(
        requestWithCookies({ [ACCESS_TOKEN_COOKIE]: expiredAccessToken })
      )
    ).toBe(false);
    expect(
      hasUsableSessionCookie(
        requestWithCookies({ [REFRESH_TOKEN_COOKIE]: "refresh-token" })
      )
    ).toBe(true);
  });

  it("builds login redirects with the original path as returnTo", () => {
    const url = new URL("https://app.ceq.lol/templates?category=social");
    const request = {
      nextUrl: {
        pathname: url.pathname,
        search: url.search,
        clone: () => new URL(url),
      },
    } as unknown as NextRequest;

    const redirect = buildLoginRedirect(request);

    expect(redirect.toString()).toBe(
      "https://app.ceq.lol/login?returnTo=%2Ftemplates%3Fcategory%3Dsocial"
    );
  });
});
