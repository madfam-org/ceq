import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import {
  ACCESS_TOKEN_COOKIE,
  REFRESH_TOKEN_COOKIE,
} from "@/lib/session-cookies";
import { isJwtExpired } from "@/lib/jwt";

const APP_HOSTNAMES = new Set([
  "app.ceq.lol",
  // Local dev — accept localhost as the app surface for now since landing
  // hostname split is operator-routed (separate Cloudflare tunnel route +
  // K8s ingress).
  "localhost",
  "localhost:5801",
]);

export function isAppHost(host: string): boolean {
  return (
    APP_HOSTNAMES.has(host) ||
    host.startsWith("app.") ||
    host.startsWith("127.0.0.1")
  );
}

export function isPublicAppPath(pathname: string): boolean {
  return (
    pathname === "/login" ||
    pathname.startsWith("/login/") ||
    pathname === "/auth" ||
    pathname.startsWith("/auth/") ||
    pathname === "/legal" ||
    pathname.startsWith("/legal/") ||
    pathname === "/api/auth" ||
    pathname.startsWith("/api/auth/")
  );
}

export function hasUsableSessionCookie(request: NextRequest): boolean {
  const accessToken = request.cookies.get(ACCESS_TOKEN_COOKIE)?.value;
  const refreshToken = request.cookies.get(REFRESH_TOKEN_COOKIE)?.value;

  if (refreshToken) return true;
  return Boolean(accessToken && !isJwtExpired(accessToken));
}

export function buildLoginRedirect(request: NextRequest): URL {
  const url = request.nextUrl.clone();
  const returnTo = `${url.pathname}${url.search}`;
  url.pathname = "/login";
  url.search = "";
  url.searchParams.set("returnTo", returnTo || "/");
  return url;
}

export function middleware(request: NextRequest) {
  const host = request.headers.get("host") ?? "";
  const { pathname, search } = request.nextUrl;

  const appHost = isAppHost(host);
  const protocol =
    request.headers.get("x-forwarded-proto") === "http" ? "http" : "https";

  if (!appHost) {
    // Marketing host (ceq.lol). Root path rewrites server-side to the
    // dedicated /landing route. The previous design used a CLIENT-side
    // window.location check inside a "use client" page; Cloudflare cached
    // the SSR HTML (cache-control: s-maxage=31536000) without a Vary on
    // Host, so ceq.lol and app.ceq.lol shared one cache entry — and
    // ceq.lol started serving the studio shell ("›Workflows / ›Queue")
    // instead of the marketing landing. Splitting onto its own URL gives
    // each host its own cache entry without needing Vary: Host (which
    // downstream proxies handle inconsistently).
    if (pathname === "/" || pathname === "") {
      const url = request.nextUrl.clone();
      url.pathname = "/landing";
      return NextResponse.rewrite(url);
    }
    if (pathname.startsWith("/landing") || pathname.startsWith("/legal")) {
      return NextResponse.next();
    }
    return NextResponse.redirect(
      `${protocol}://app.ceq.lol${pathname}${search}`,
      307,
    );
  }

  if (pathname.startsWith("/landing")) {
    return NextResponse.redirect(`${protocol}://ceq.lol/`, 307);
  }

  if (!isPublicAppPath(pathname) && !hasUsableSessionCookie(request)) {
    return NextResponse.redirect(buildLoginRedirect(request), 307);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml).*)",
  ],
};
