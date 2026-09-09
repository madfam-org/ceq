#!/usr/bin/env bash
# Boot the built Studio standalone tree and check the wire for Next's internal
# rewrite header.
#
# WHY THIS EXISTS ALONGSIDE studio-docker-smoke.sh
#
# That script needs Docker and a built image; this one needs only `pnpm --filter
# @ceq/studio build`, so it runs in the plain `studio` CI job and on a laptop.
# The two check different things and neither replaces the other: the Docker one
# proves the IMAGE starts, this one proves the SERVER does not leak.
#
# WHY IT IS NOT A UNIT TEST
#
# The header is written by Next's ROUTER SERVER, in code no test of
# src/middleware.ts can reach. The middleware's own response object MUST carry
# `x-middleware-rewrite` — that is where Next reads the rewrite from — so a unit
# test asserting its absence there would be asserting that the rewrite does not
# happen. "Does a visitor see it?" only has an answer over real HTTP.
#
# WHAT IT ASSERTS
#
#   1. `GET / Host: ceq.lol` still SERVES the landing page — 200 with a non-empty
#      body. Removing the header the wrong way (deleting it inside the
#      middleware) also makes it absent, and turns this into a blank 200 with no
#      error. Both halves or neither.
#   2. `x-middleware-rewrite` is ABSENT from that response.
#   3. The `next.config.mjs` security headers still arrive. This patch sits in
#      front of every header the process sends; a loosened matcher would take the
#      Selva Atrium frame-ancestors policy with it and nothing visible would
#      change.
#   4. The boot line says the filter installed. Without this, a build that
#      stopped rewriting entirely would satisfy (2) vacuously.
#   5. No `Failed to proxy` in the log — the loudest signal in this class, and
#      the only one that exists when a rewrite is proxied to a foreign origin
#      instead of routed internally.
#
# THE BOOT HOSTNAME IS PART OF THE TEST
#
# This binds 0.0.0.0, which is what apps/studio/Dockerfile sets. Booting
# 127.0.0.1 would be a DIFFERENT configuration, not a convenience: Next composes
# initUrl from the bound hostname and Node canonicalises the loopback literal, so
# the origins stop comparing equal and Next PROXIES the rewrite rather than
# routing it — the bug then looks fixed when it is not. Keep this in agreement
# with the Dockerfile; it is the same knob.
#
# Usage:
#   pnpm --filter @ceq/studio build
#   bash scripts/studio-standalone-header-smoke.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STANDALONE="${REPO_ROOT}/apps/studio/.next/standalone"
PORT="${STUDIO_HEADER_SMOKE_PORT:-15811}"
# ceq.lol is the marketing host: the middleware rewrites its root to /landing,
# and it needs no session. An assertion behind the app host's auth gate would
# pass vacuously against a redirect to /login.
HOST_HEADER="${STUDIO_HEADER_SMOKE_HOST:-ceq.lol}"

failures=0
checks=0

pass() { checks=$((checks + 1)); printf '  ok   %s\n' "$1"; }
fail() {
  checks=$((checks + 1))
  failures=$((failures + 1))
  printf '  FAIL %s\n' "$1" >&2
}

if [ ! -d "$STANDALONE" ]; then
  echo "FAIL: no ${STANDALONE}." >&2
  echo "      Run: pnpm --filter @ceq/studio build" >&2
  echo "      A smoke that examined nothing has not passed." >&2
  exit 1
fi

# The image copies these next to server.js; a source tree has not.
mkdir -p "${STANDALONE}/apps/studio/.next" "${STANDALONE}/apps/studio/public"
if [ -d "${REPO_ROOT}/apps/studio/.next/static" ]; then
  cp -R "${REPO_ROOT}/apps/studio/.next/static" "${STANDALONE}/apps/studio/.next/static" 2>/dev/null || true
fi
cp "${REPO_ROOT}/apps/studio/server-entry.mjs" "${STANDALONE}/apps/studio/server-entry.mjs"

# REFUSE TO RUN AGAINST SOMEBODY ELSE'S SERVER.
#
# This is not defensive tidiness — it is the failure this script was caught by
# while being written. A previous run's node process survived its cleanup and
# kept port 15811, so the next invocation bound nothing, curled the OLD server,
# and a deliberately-gutted entry with no filter at all scored 7/7. A smoke that
# reports on a process it did not start is worse than no smoke.
if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:${PORT}/" 2>/dev/null; then
  echo "FAIL: something is already listening on 127.0.0.1:${PORT}." >&2
  echo "      This script would have tested THAT server and reported on it as if" >&2
  echo "      it were the build under test. Stop it, or set" >&2
  echo "      STUDIO_HEADER_SMOKE_PORT to a free port." >&2
  exit 1
fi

LOG="$(mktemp)"
cleanup() {
  if [ -n "${SERVER_PID:-}" ]; then
    # Kill the whole process group, not the pid. `node` is started inside a
    # subshell, so $! is the subshell; signalling it alone leaves the server
    # holding the port — which is exactly how the stale-listener false green
    # above happened.
    kill -9 -- "-${SERVER_PID}" 2>/dev/null || kill -9 "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -f "$LOG"
}
trap cleanup EXIT

echo "Booting apps/studio/server-entry.mjs on 0.0.0.0:${PORT} (the Dockerfile's HOSTNAME)"
# `set -m` puts the background job in its own process group so the cleanup above
# can signal the whole tree.
set -m
(
  cd "$STANDALONE" || exit 1
  PORT="$PORT" HOSTNAME=0.0.0.0 NODE_ENV=production exec node apps/studio/server-entry.mjs
) >"$LOG" 2>&1 &
SERVER_PID=$!
set +m

ready=0
for _ in $(seq 1 60); do
  if curl -s -o /dev/null "http://127.0.0.1:${PORT}/" 2>/dev/null; then
    ready=1
    break
  fi
  sleep 0.5
done

if [ "$ready" -ne 1 ]; then
  echo "FAIL: server never accepted a connection. Log:" >&2
  cat "$LOG" >&2
  exit 1
fi

# One request, headers and body captured separately. No pipelines around the
# assertions: a GitHub Actions `run:` has no pipefail, so `cmd | tee || rc=$?`
# never fires — this keeps its own counter and exits explicitly.
HEADERS="$(mktemp)"
BODY="$(mktemp)"
curl -s -D "$HEADERS" -o "$BODY" -H "Host: ${HOST_HEADER}" "http://127.0.0.1:${PORT}/"
status="$(head -1 "$HEADERS" | awk '{print $2}')"
bytes="$(wc -c <"$BODY" | tr -d ' ')"

# (1) The rewrite still resolves — both halves.
if [ "$status" = "200" ]; then
  pass "GET / Host: ${HOST_HEADER} -> 200"
else
  fail "GET / Host: ${HOST_HEADER} -> ${status}, expected 200"
fi
if [ "$bytes" -gt 0 ]; then
  pass "body is ${bytes} bytes, not the blank 200 of a cancelled rewrite"
else
  fail "EMPTY BODY — this is what deleting x-middleware-rewrite inside src/middleware.ts produces: the rewrite is cancelled, not hidden"
fi

# (2) The header is not on the wire.
if grep -qi '^x-middleware-rewrite:' "$HEADERS"; then
  fail "$(grep -i '^x-middleware-rewrite:' "$HEADERS" | tr -d '\r') reached the client"
else
  pass "x-middleware-rewrite absent"
fi

# (3) The headers this app sets on purpose survived the filter.
if grep -qi '^x-frame-options:' "$HEADERS"; then
  pass "x-frame-options still present"
else
  fail "x-frame-options is gone — the filter is dropping more than Next's own names"
fi
if grep -qi '^content-security-policy:' "$HEADERS"; then
  pass "content-security-policy still present"
else
  fail "content-security-policy is gone — the Selva Atrium frame-ancestors policy would be unset"
fi

# (4) Anti-vacuity: (2) is also satisfied by a build that stopped rewriting.
if grep -q 'ceq-studio: internal response header filter active' "$LOG"; then
  pass "the entry reported installing the filter"
else
  fail "no filter boot line in the log — the process that answered may be Next's own server.js, in which case the absent header above proves nothing"
fi

# (5) The loudest signal in this class.
if grep -q 'Failed to proxy' "$LOG"; then
  fail "the log says 'Failed to proxy' — the rewrite is going to a foreign origin instead of being routed. Check the boot HOSTNAME against apps/studio/Dockerfile"
  sed -n '1,40p' "$LOG" >&2
else
  pass "no 'Failed to proxy' in the log"
fi

rm -f "$HEADERS" "$BODY"

echo ""
echo "$((checks - failures))/${checks} checks passed."
if [ "$failures" -gt 0 ]; then exit 1; fi
exit 0
