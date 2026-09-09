/**
 * The process entry for the Studio container. Installs one response-header
 * filter, then hands over to Next's generated standalone server.
 *
 * ── What leaks ───────────────────────────────────────────────────────────────
 *
 * The middleware rewrites the marketing host's root onto the landing route, and
 * Next answers the visitor with a header naming that internal route:
 *
 *   GET / Host: ceq.lol
 *   -> 200
 *      x-middleware-rewrite: /landing
 *
 * Measured on this repository's own `.next/standalone` at Next 14.2.35, bound to
 * 0.0.0.0 as the Dockerfile binds it. `ceq.lol` is the public marketing surface,
 * so this reaches every anonymous visitor to the site's front page.
 *
 * ── Why it is Next's defect and not this app's misconfiguration ─────────────
 *
 * `x-middleware-rewrite` is Next's internal router signal, and Next classifies
 * it as internal itself: it is the FIRST entry of `INTERNAL_HEADERS` in
 * `next/dist/server/lib/server-ipc/utils.js`, the list Next uses to strip these
 * names from INBOUND requests so a caller cannot forge one
 * (`router-server.js` calls `filterInternalHeaders(req.headers)`). The same list
 * is never applied on the way OUT:
 *
 *   // next/dist/server/lib/router-utils/resolve-routes.js:406
 *   if (middlewareHeaders["x-middleware-rewrite"]) {
 *     const value = middlewareHeaders["x-middleware-rewrite"];
 *     const rel = relativizeURL(value, initUrl);
 *     resHeaders["x-middleware-rewrite"] = rel;   // <- the client copy
 *     parsedUrl = url.parse(rel, true);           // <- the actual routing
 *   }
 *
 *   // next/dist/server/lib/router-server.js:258
 *   for (const key of Object.keys(resHeaders || {})) {
 *     res.setHeader(key, resHeaders[key]);        // <- onto the wire
 *   }
 *
 * There is no origin comparison and no configuration option that suppresses it.
 * `vercel/next.js#58366` is open with no official fix; what people deploy is an
 * nginx `proxy_hide_header`, a Cloudflare rule, or `patch-package`.
 *
 * ── Why the fix is NOT in `src/middleware.ts` ────────────────────────────────
 *
 * That is where it looks like it goes, and it is the one move that must never be
 * made, because it fails SILENTLY. Read the snippet again: the same value that
 * becomes the client header on one line is what `parsedUrl` is built from on the
 * next. Next reads the rewrite out of the middleware's own response object, so
 * deleting it there does not hide the rewrite — it CANCELS it, and `ceq.lol/`
 * becomes an empty 200 with no error and no log line.
 *
 * `next.config.mjs`'s `headers()` cannot do it either. Those header routes are
 * applied EARLIER in the same route list than the middleware branch that writes
 * the value, so they run before it exists. (The `X-Frame-Options` and CSP
 * entries there are unaffected by this file and are asserted to survive it in
 * `__tests__/internal-response-headers.test.ts`.)
 *
 * ── So it is done on the Node response, after Next has already routed ────────
 *
 * By the time `router-server.js` calls `res.setHeader`, `parsedUrl` is computed
 * and the rewrite is decided. Dropping the header THERE removes the wire copy
 * and changes no routing — asserted both ways: the unit test pins that only the
 * internal name falls and everything else passes, and
 * `scripts/studio-header-smoke.sh` proves over real HTTP that the landing page
 * still renders while the header is gone.
 *
 * ── Plain `.mjs`, next to server.js, and why it is not TypeScript ────────────
 *
 * The standalone tree ships no TypeScript compiler and no bundler, so this
 * cannot import from `src/`. It sits beside `apps/studio/server.js` because that
 * is what it imports, and the Dockerfile copies it there.
 *
 * WHY NOT `instrumentation.ts`: that hook is compiled for the edge runtime too,
 * where `node:http` does not exist, and it is loaded LAZILY by the render server
 * while this header is written by the ROUTER server. Patching here runs before
 * Next's server module is evaluated, so the filter is in place before the
 * listener binds and no request can arrive ahead of it.
 */

import http from "node:http";

/**
 * Response headers Next writes for its own router and must not put on the wire.
 *
 * One name today, and deliberately a list: `x-middleware-rewrite` is the one
 * this app provably emits, but Next's own `INTERNAL_HEADERS` holds seven more
 * and `x-middleware-redirect` and `x-matched-path` would reach `resHeaders` by
 * the same unconditional copy if a future branch produced them.
 *
 * ONLY NAMES NEXT SETS FOR ITSELF BELONG HERE. Anything a page, a route handler
 * or `next.config.mjs` sets deliberately must pass through untouched.
 */
const INTERNAL_RESPONSE_HEADERS = ["x-middleware-rewrite"];

const blocked = new Set(INTERNAL_RESPONSE_HEADERS);
const proto = http.ServerResponse.prototype;

/**
 * Marker proving the patch is installed, so a double import cannot wrap
 * `setHeader` twice. A symbol rather than a string property: it must not appear
 * in `Object.keys` of anything.
 */
const installed = Symbol.for("ceq.internal-response-headers.installed");

if (proto[installed] !== true) {
  const original = proto.setHeader;
  proto.setHeader = function patchedSetHeader(name, value) {
    // `return this`, not undefined: `setHeader` is documented to return the
    // response for chaining, and Next relies on the ServerResponse contract.
    if (typeof name === "string" && blocked.has(name.toLowerCase())) return this;
    return original.call(this, name, value);
  };
  proto[installed] = true;
}

// Read proof rather than a comment claiming the patch is on. A boot that did not
// install the filter must be distinguishable in the log from one that did — this
// is what the smoke checks alongside the absent-header assertion, because
// "header absent" on its own is also what a build that stopped rewriting looks
// like.
console.log(
  `ceq-studio: internal response header filter active for ${INTERNAL_RESPONSE_HEADERS.join(", ")}`,
);

// Next's generated standalone server. It calls `process.chdir(__dirname)` and
// binds the listener, so nothing may be added after this point.
await import("./server.js");
