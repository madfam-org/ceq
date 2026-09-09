#!/usr/bin/env bash
# Smoke-test a locally loaded ceq-studio Docker image.
#
# Guards against the 2026-05-18 class of failures where the container
# starts with `node server.js` but Next.js standalone output (with
# outputFileTracingRoot) places the entrypoint at apps/studio/server.js.
#
# Also checks that the image does not publish Next's internal
# `x-middleware-rewrite` header. That one is the IMAGE's half of the check:
# scripts/studio-standalone-header-smoke.sh proves the server code is clean, but
# only this can prove the CMD actually starts the filtered entry — an image built
# from a Dockerfile whose CMD still named server.js would pass every other gate
# in the repository and leak in production.
#
# Usage:
#   docker build -f apps/studio/Dockerfile -t ceq-studio:smoke .
#   scripts/studio-docker-smoke.sh ceq-studio:smoke

set -euo pipefail

IMAGE="${1:-ceq-studio:smoke}"
PORT="${STUDIO_SMOKE_PORT:-15801}"
HEALTH_PATH="${STUDIO_SMOKE_PATH:-/}"
MAX_ATTEMPTS="${STUDIO_SMOKE_ATTEMPTS:-30}"
SLEEP_SECONDS="${STUDIO_SMOKE_SLEEP_SECONDS:-2}"

log() {
  printf '[studio-docker-smoke] %s\n' "$*" >&2
}

fail() {
  printf '[studio-docker-smoke] ERROR: %s\n' "$*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

need docker
need curl

log "Verifying server entrypoint in image ${IMAGE}"
docker run --rm --entrypoint sh "$IMAGE" -c 'test -f apps/studio/server.js' \
  || fail "apps/studio/server.js missing in image"
docker run --rm --entrypoint sh "$IMAGE" -c 'test -f apps/studio/server-entry.mjs' \
  || fail "apps/studio/server-entry.mjs missing in image — the CMD starts it"

log "Starting container on port ${PORT}"
CID="$(docker run -d --rm -p "${PORT}:5801" "$IMAGE")"
trap 'docker rm -f "$CID" >/dev/null 2>&1 || true' EXIT

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  if curl -sf "http://127.0.0.1:${PORT}${HEALTH_PATH}" >/dev/null; then
    log "HTTP OK on attempt ${attempt}"

    # The marketing host's root is rewritten to /landing, and Next puts the
    # internal route name on the client response unless the entry filters it.
    # `ceq.lol` needs no session, so this cannot pass vacuously against a
    # redirect to the login wall.
    headers="$(mktemp)"
    body="$(mktemp)"
    curl -s -D "$headers" -o "$body" -H 'Host: ceq.lol' "http://127.0.0.1:${PORT}/"

    if grep -qi '^x-middleware-rewrite:' "$headers"; then
      log "Container logs:"
      docker logs "$CID" 2>&1 | tail -30 >&2 || true
      rm -f "$headers" "$body"
      fail "the image publishes $(grep -i '^x-middleware-rewrite:' "$headers" | tr -d '\r')"
    fi
    log "x-middleware-rewrite absent from the image's response"

    # Both halves. Removing the header the wrong way — deleting it inside
    # src/middleware.ts — also makes it absent, and serves a blank 200.
    if [ ! -s "$body" ]; then
      rm -f "$headers" "$body"
      fail "empty body on the rewritten path: the rewrite was cancelled, not filtered"
    fi
    log "rewritten path served $(wc -c <"$body" | tr -d ' ') bytes"
    rm -f "$headers" "$body"

    # Anti-vacuity: an absent header is also what an image that stopped
    # rewriting looks like. The entry says on boot whether it installed.
    if docker logs "$CID" 2>&1 | grep -q 'ceq-studio: internal response header filter active'; then
      log "the entry reported installing the filter"
    else
      log "Container logs:"
      docker logs "$CID" 2>&1 | tail -30 >&2 || true
      fail "no filter boot line — the CMD may still be starting server.js directly"
    fi

    # The loudest signal in this class: a proxied rewrite rather than a routed
    # one, which is what a HOSTNAME mismatch produces.
    if docker logs "$CID" 2>&1 | grep -q 'Failed to proxy'; then
      docker logs "$CID" 2>&1 | tail -30 >&2 || true
      fail "the container log says 'Failed to proxy' — the rewrite is not being routed internally"
    fi
    log "no 'Failed to proxy' in the container log"

    exit 0
  fi
  sleep "$SLEEP_SECONDS"
done

log "Container logs:"
docker logs "$CID" 2>&1 | tail -50 >&2 || true
fail "Studio container did not become healthy on port ${PORT}"
