import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const APP_HOSTNAMES = new Set([
  "app.ceq.lol",
  // Local dev — accept localhost as the app surface for now since landing
  // hostname split is operator-routed (separate Cloudflare tunnel route +
  // K8s ingress).
  "localhost",
  "localhost:5801",
]);

export function middleware(request: NextRequest) {
  const host = request.headers.get("host") ?? "";
  const { pathname, search } = request.nextUrl;

  const isAppHost = APP_HOSTNAMES.has(host) || host.startsWith("app.");

  if (!isAppHost) {
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
    if (
      pathname.startsWith("/auth/") ||
      pathname.startsWith("/api/") ||
      pathname.startsWith("/landing")
    ) {
      return NextResponse.next();
    }
    const protocol =
      request.headers.get("x-forwarded-proto") === "http" ? "http" : "https";
    return NextResponse.redirect(
      `${protocol}://app.ceq.lol${pathname}${search}`,
      307,
    );
  }

  // App host (app.ceq.lol). Studio renders at `/`; unauthenticated visitors
  // fall through to the landing component inside page.tsx, but on the
  // app's own URL/cache entry — no cross-host cache pollution.
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml).*)",
  ],
};
