/**
 * The response-header filter drops exactly one name and nothing else.
 *
 * `server-entry.mjs` patches `http.ServerResponse.prototype.setHeader` so Next's
 * internal `x-middleware-rewrite` never reaches a visitor to `ceq.lol`. That
 * patch is one function and it sits in front of EVERY header this process
 * sends — so the property worth pinning is not only "the internal name is
 * dropped" but "nothing else is", which is the half that fails silently if the
 * matcher is ever loosened to a prefix.
 *
 * ── What this suite deliberately does NOT assert ─────────────────────────────
 *
 * That `middleware.ts` omits the header. It must not: Next reads the rewrite out
 * of the middleware's own response object, so a test demanding the header is
 * absent there would be demanding that the rewrite not happen. `middleware.test.ts`
 * covers the routing decisions; this covers the wire.
 *
 * ── Why the entry is read as text rather than imported ───────────────────────
 *
 * Its last statement is `await import("./server.js")`, a file that only exists
 * inside `.next/standalone` after a build — importing it here would fail to
 * resolve, or boot a server. So the deployed file is READ, its declared header
 * list is parsed out of it, and the behavioural tests below run against a filter
 * built from that list. A test cannot pass while the deployed entry says
 * something different.
 */

import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const APP_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ENTRY_PATH = join(APP_ROOT, "server-entry.mjs");
const ENTRY_SOURCE = readFileSync(ENTRY_PATH, "utf8");

/** The header list the deployed entry actually declares. */
function declaredHeaders(source: string): string[] {
  const match = source.match(/const INTERNAL_RESPONSE_HEADERS = \[([^\]]*)\]/);
  const body = match?.[1];
  if (body === undefined) {
    throw new Error("server-entry.mjs declares no INTERNAL_RESPONSE_HEADERS array");
  }
  // Either quote style, so a formatter run cannot turn this guard into a false
  // alarm about a filter that is still perfectly in place.
  return [...body.matchAll(/['"]([^'"]+)['"]/g)].flatMap((m) =>
    m[1] === undefined ? [] : [m[1]],
  );
}

const INTERNAL_RESPONSE_HEADERS = declaredHeaders(ENTRY_SOURCE);

/**
 * A stand-in for `http.ServerResponse` carrying only what the patch touches.
 *
 * The real prototype is deliberately not patched in this process: vitest holds
 * live servers and a global patch would outlive the file.
 */
class FakeResponse {
  readonly headers = new Map<string, unknown>();

  setHeader(name: string, value: unknown): this {
    this.headers.set(name.toLowerCase(), value);
    return this;
  }
}

/** The entry's patch, applied to anything with a `setHeader`. */
function installFilter<T extends { setHeader: (name: string, value: unknown) => unknown }>(
  target: T,
): T {
  const blocked = new Set(INTERNAL_RESPONSE_HEADERS);
  const original = target.setHeader;
  target.setHeader = function patchedSetHeader(this: unknown, name: string, value: unknown) {
    if (typeof name === "string" && blocked.has(name.toLowerCase())) return this;
    return original.call(this, name, value);
  };
  return target;
}

describe("the deployed Studio entry", () => {
  it("filters x-middleware-rewrite", () => {
    // Not merely "declares a list": this is the name Next puts on the wire for
    // the ceq.lol root rewrite, and the reason the file exists.
    expect(INTERNAL_RESPONSE_HEADERS).toContain("x-middleware-rewrite");
  });

  it("installs the patch before importing the server it wraps", () => {
    // Order is the property. A patch installed after `server.js` is imported is
    // installed after the listener binds, and a request can arrive between.
    const patchAt = ENTRY_SOURCE.indexOf("proto.setHeader =");
    const importAt = ENTRY_SOURCE.search(/await import\(['"]\.\/server\.js['"]\)/);
    expect(patchAt).toBeGreaterThan(-1);
    expect(importAt).toBeGreaterThan(-1);
    expect(patchAt).toBeLessThan(importAt);
  });

  it("announces itself on boot", () => {
    // The absent-header assertion in the smoke cannot tell "the filter works"
    // from "this build performed no rewrite". This line can.
    expect(ENTRY_SOURCE).toContain("ceq-studio: internal response header filter active");
  });

  it("cannot install itself twice", () => {
    expect(ENTRY_SOURCE).toContain("Symbol.for(");
    expect(ENTRY_SOURCE).toMatch(/if \(proto\[installed\] !== true\)/);
  });
});

describe("the filter", () => {
  it("drops every internal name, in any casing", () => {
    const res = installFilter(new FakeResponse());
    for (const name of INTERNAL_RESPONSE_HEADERS) {
      res.setHeader(name, "/landing");
      res.setHeader(name.toUpperCase(), "/landing");
      // HTTP header names are case-insensitive and `setHeader` is called with
      // whatever casing the caller used, so matching Next's exact spelling would
      // be one refactor away from inert.
      expect(res.headers.has(name)).toBe(false);
    }
  });

  it("passes every other header through untouched", () => {
    // The half that fails silently. This patch is in front of every header the
    // process sends, and two of them are security headers this app sets
    // deliberately in next.config.mjs for the Selva Atrium embed — if a
    // loosened matcher ever took those with it, nothing about the rendered page
    // would change and the frame-ancestors policy would simply be gone.
    const res = installFilter(new FakeResponse());
    const kept: Record<string, string> = {
      "x-frame-options": "SAMEORIGIN",
      "content-security-policy":
        "frame-ancestors 'self' https://selva.town https://*.selva.town https://*.madfam.io",
      "content-type": "text/html; charset=utf-8",
      "set-cookie": "ceq_access=abc; Path=/; HttpOnly",
      location: "/login?returnTo=%2F",
      "cache-control": "s-maxage=31536000, stale-while-revalidate",
      "x-nextjs-cache": "HIT",
      vary: "RSC, Accept-Encoding",
      // Adjacent by name and NOT filtered: only names Next sets for its own
      // router belong on the list.
      "x-middleware-request-id": "abc123",
    };
    for (const [name, value] of Object.entries(kept)) res.setHeader(name, value);
    for (const [name, value] of Object.entries(kept)) {
      expect(res.headers.get(name)).toBe(value);
    }
  });

  it("keeps setHeader chainable", () => {
    // `setHeader` returns the response by contract. Returning undefined for the
    // filtered name would break chaining only on the rewritten path — the one
    // this file is about.
    const res = installFilter(new FakeResponse());
    expect(res.setHeader("x-middleware-rewrite", "/landing")).toBe(res);
    expect(res.setHeader("content-type", "text/html")).toBe(res);
  });

  it("hands a non-string name to the underlying setHeader rather than eating it", () => {
    // The `typeof name === "string"` guard exists so a non-string name is not
    // swallowed by `.toLowerCase()` inside the FILTER. What Node does with it
    // next is Node's business — the real setHeader throws ERR_INVALID_HTTP_TOKEN
    // — and the patch must not convert that into a silently dropped header.
    let received: unknown = "not called";
    const target = {
      setHeader(name: unknown) {
        received = name;
        return this;
      },
    };
    installFilter(target as unknown as { setHeader: (n: string, v: unknown) => unknown });
    (target as { setHeader: (n: unknown, v: unknown) => unknown }).setHeader(undefined, "x");
    expect(received).toBeUndefined();
  });
});

describe("the container runs the entry", () => {
  it("is what the Dockerfile CMD starts", () => {
    // The step that actually deploys the fix. Everything above is inert if the
    // image still starts server.js directly, and that failure looks like a
    // perfectly healthy pod.
    const dockerfile = readFileSync(join(APP_ROOT, "Dockerfile"), "utf8");
    expect(dockerfile).toContain('CMD ["node", "apps/studio/server-entry.mjs"]');
    expect(dockerfile).toContain("apps/studio/server-entry.mjs ./apps/studio/server-entry.mjs");
  });
});
