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
    if (pathname === "/" || pathname === "") {
      return NextResponse.next();
    }
    if (
      pathname.startsWith("/auth/") ||
      pathname.startsWith("/api/")
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

  if (isAppHost && (pathname === "/" || pathname === "")) {
    return NextResponse.next();
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml).*)",
  ],
};
