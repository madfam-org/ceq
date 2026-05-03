/**
 * Landing route — served at ceq.lol via middleware rewrite of `/` → `/landing`
 * for non-`app.*` hosts.
 *
 * Splitting the marketing surface onto its own route is what gives us
 * per-route cache isolation. The previous client-side `window.location.host`
 * gate inside a `"use client"` page rendered the same SSR HTML for both
 * `ceq.lol` and `app.ceq.lol`; Cloudflare cached one variant (with
 * `cache-control: s-maxage=31536000`) and served it for both hosts —
 * which is why ceq.lol started serving the studio "›Workflows / ›Queue"
 * shell instead of the marketing landing.
 *
 * The route-level split fixes that without needing `Vary: Host` (which
 * downstream CDNs/proxies handle inconsistently).
 */
import { MarketingLanding } from "@/components/landing/marketing-landing";

export default function LandingPage() {
  return <MarketingLanding />;
}
