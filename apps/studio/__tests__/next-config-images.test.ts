/**
 * The image optimizer stays off, and the remote image allowlist stays exact.
 *
 * `images.unoptimized` makes Next answer `/_next/image` with a 404 before it
 * reads a parameter or fetches anything, and makes every `<Image>` render a
 * plain `<img>` with its original `src`. It used to be true only in
 * development, which is the one environment that never serves visitors.
 *
 * The config is evaluated with NODE_ENV=production because that is what the
 * Docker build runs with; an environment-conditional value would pass under
 * vitest's own NODE_ENV and still ship the optimizer.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

type RemotePattern = {
  protocol?: string;
  hostname: string;
  port?: string;
  pathname?: string;
};

type ImagesConfig = {
  unoptimized?: boolean;
  loader?: string;
  remotePatterns?: RemotePattern[];
  domains?: string[];
};

async function loadImagesConfig(nodeEnv: string): Promise<ImagesConfig> {
  vi.resetModules();
  vi.stubEnv("NODE_ENV", nodeEnv);
  const mod = await import("../next.config.mjs");
  return (mod.default as { images: ImagesConfig }).images;
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("next.config.mjs images", () => {
  it.each(["production", "development", "test"])(
    "keeps the optimizer off when NODE_ENV=%s",
    async (nodeEnv) => {
      const images = await loadImagesConfig(nodeEnv);
      expect(images.unoptimized).toBe(true);
    },
  );

  it("allows no wildcard host and no plain-http origin", async () => {
    const images = await loadImagesConfig("production");
    expect(images.domains ?? []).toEqual([]);
    const patterns = images.remotePatterns ?? [];
    expect(patterns.length).toBeGreaterThan(0);
    for (const pattern of patterns) {
      expect(pattern.protocol).toBe("https");
      expect(pattern.hostname).not.toContain("*");
      expect(pattern.pathname).toBeDefined();
    }
  });
});
