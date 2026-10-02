import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Enable standalone output for Docker deployment
  output: "standalone",
  // Skip build-time type errors (stubs for slider/switch have type mismatches)
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
  // Trace from monorepo root to include workspace deps in standalone.
  // Top-level since Next 15 (it lived under `experimental` on 14.x).
  outputFileTracingRoot: path.join(__dirname, "../../"),
  experimental: {
    // Enable React Server Components
    serverActions: {
      bodySizeLimit: "10mb",
    },
  },
  images: {
    // Next's built-in image optimizer is OFF in every environment
    // (GHSA-2xp9-vwfh-vxw4; no fix exists on the 14.x line). With this set,
    // `/_next/image` answers 404 before it reads any parameter or fetches any
    // URL, and every `<Image>` renders a plain `<img>` with its original `src`
    // (no srcset); `fill`, `width`/`height` and `priority` still lay out the
    // same. Thumbnails are therefore served at their stored size. Re-enabling
    // resizing means a custom `loader` that resizes at the CDN, not flipping
    // this back. Asserted in __tests__/next-config-images.test.ts.
    unoptimized: true,
    // Only consulted by the optimizer, so inert while `unoptimized` is true;
    // kept to the exact origins the app's images come from so that a future
    // re-enable does not inherit a wildcard. No `*` in any hostname.
    remotePatterns: [
      {
        // The R2 account endpoint the API builds `public_url` from when
        // R2_PUBLIC_URL is unset (`{R2_ENDPOINT}/{bucket}/{key}`, see
        // apps/api/src/ceq_api/storage/__init__.py). Account id and bucket as
        // documented in docs/PRODUCTION_DEPLOYMENT.md.
        protocol: "https",
        hostname: "12f1353f7819865c56161ce00297668e.r2.cloudflarestorage.com",
        pathname: "/ceq-assets/**",
      },
      {
        // The public CDN domain for the same bucket (R2_PUBLIC_URL).
        protocol: "https",
        hostname: "assets.ceq.lol",
        pathname: "/**",
      },
    ],
  },
  // Environment variables
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:5800",
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:5820",
  },
  // Selva Atrium iframe allowance.
  // The Atrium is the consumer-side feature in selva-office that surfaces every
  // MADFAM platform as a window into a single welcoming central space. Permitting
  // selva.town as a frame-ancestor lets the Atrium embed ceq.lol. X-Frame-Options:
  // SAMEORIGIN remains as a legacy fallback. App-wide; auth surfaces inherit the
  // same policy. Acceptable because Innovaciones MADFAM runs both Selva and CEQ.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          {
            key: "Content-Security-Policy",
            value:
              "frame-ancestors 'self' https://selva.town https://*.selva.town https://*.madfam.io",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
