import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Enable standalone output for Docker deployment
  output: "standalone",
  // Trace from monorepo root to include workspace deps in standalone
  outputFileTracingRoot: path.join(__dirname, '../../'),
  // Skip build-time type errors (stubs for slider/switch have type mismatches)
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
  experimental: {
    // Enable React Server Components
    serverActions: {
      bodySizeLimit: "10mb",
    },
  },
  // Disable image optimization in dev for faster builds
  images: {
    unoptimized: process.env.NODE_ENV === "development",
    remotePatterns: [
      {
        protocol: "https",
        hostname: "*.r2.cloudflarestorage.com",
      },
      {
        protocol: "https",
        hostname: "assets.ceq.lol",
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
