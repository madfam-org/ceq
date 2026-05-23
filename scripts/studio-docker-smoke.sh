#!/usr/bin/env bash
# Smoke-test a locally loaded ceq-studio Docker image.
#
# Guards against the 2026-05-18 class of failures where the container
# starts with `node server.js` but Next.js standalone output (with
# outputFileTracingRoot) places the entrypoint at apps/studio/server.js.
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

log "Starting container on port ${PORT}"
CID="$(docker run -d --rm -p "${PORT}:5801" "$IMAGE")"
trap 'docker rm -f "$CID" >/dev/null 2>&1 || true' EXIT

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  if curl -sf "http://127.0.0.1:${PORT}${HEALTH_PATH}" >/dev/null; then
    log "HTTP OK on attempt ${attempt}"
    exit 0
  fi
  sleep "$SLEEP_SECONDS"
done

log "Container logs:"
docker logs "$CID" 2>&1 | tail -50 >&2 || true
fail "Studio container did not become healthy on port ${PORT}"
