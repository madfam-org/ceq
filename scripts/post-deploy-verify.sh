#!/usr/bin/env bash
# CEQ post-deploy verification — bundles public, authenticated, and optional GPU smokes.
#
# Usage:
#   source ops/smoke-config.env   # after copying from smoke-config.env.example
#   bash scripts/post-deploy-verify.sh           # public + auth (if token set)
#   bash scripts/post-deploy-verify.sh --strict  # + operations status, cancel, credits
#   bash scripts/post-deploy-verify.sh --gpu     # + template golden path
#   bash scripts/post-deploy-verify.sh --all     # strict + gpu
#
# Writes evidence stub to ops/evidence/ when CEQ_WRITE_EVIDENCE=true (default).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SMOKE_SCRIPT="${REPO_ROOT}/scripts/production-smoke.sh"
EVIDENCE_DIR="${REPO_ROOT}/ops/evidence"
WRITE_EVIDENCE="${CEQ_WRITE_EVIDENCE:-true}"

MODE="default"
for arg in "$@"; do
  case "$arg" in
    --strict) MODE="strict" ;;
    --gpu) MODE="gpu" ;;
    --all) MODE="all" ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

log() { printf '[post-deploy] %s\n' "$*" >&2; }

if [[ ! -x "$SMOKE_SCRIPT" ]]; then
  chmod +x "$SMOKE_SCRIPT"
fi

TIMESTAMP="$(date -u +%Y-%m-%dT%H%M%SZ)"
EVIDENCE_FILE="${EVIDENCE_DIR}/${TIMESTAMP}-post-deploy-verify.md"

run_smoke() {
  local label="$1"
  shift
  log "Running: $label"
  # Remaining args are env KEY=VALUE pairs forwarded to production-smoke.sh
  if env "$@" bash "$SMOKE_SCRIPT"; then
    log "PASS: $label"
    echo "- [x] $label" >> "$EVIDENCE_FILE"
    return 0
  fi
  log "FAIL: $label"
  echo "- [ ] $label (FAILED)" >> "$EVIDENCE_FILE"
  return 1
}

mkdir -p "$EVIDENCE_DIR"

if [[ "$WRITE_EVIDENCE" == "true" ]]; then
  cat > "$EVIDENCE_FILE" <<EOF
# Post-deploy verification — ${TIMESTAMP}

- API: ${CEQ_API_URL:-https://api.ceq.lol}
- App: ${CEQ_APP_URL:-https://app.ceq.lol}
- Mode: ${MODE}
- Operator: $(whoami)@$(hostname -s 2>/dev/null || echo local)

## Results

EOF
fi

FAILED=0

# Always run public smoke
run_smoke "public smoke" CEQ_PUBLIC_ONLY=true || FAILED=1

if [[ -z "${CEQ_AUTH_TOKEN:-}" ]]; then
  log "SKIP: authenticated checks (CEQ_AUTH_TOKEN not set)"
  echo "- [ ] authenticated smoke (SKIPPED — no CEQ_AUTH_TOKEN)" >> "$EVIDENCE_FILE"
else
  run_smoke "authenticated credits balance" \
    CEQ_REQUIRE_CREDITS_ROUTE=true \
    || FAILED=1

  run_smoke "authenticated templates seeded" \
    CEQ_REQUIRE_TEMPLATE_SEEDING=true \
    || FAILED=1

  if [[ "$MODE" == "strict" || "$MODE" == "all" ]]; then
    run_smoke "strict smoke (operations + cancel)" \
      CEQ_STRICT_SMOKE=true \
      || FAILED=1
  fi

  if [[ "$MODE" == "gpu" || "$MODE" == "all" ]]; then
    if [[ -z "${CEQ_TEMPLATE_ID:-}" ]]; then
      log "WARN: CEQ_TEMPLATE_ID not set; using FLUX SCHNELL default"
      export CEQ_TEMPLATE_ID="d8b30c7e-4501-493f-94c7-5223d7777afb"
      export CEQ_TEMPLATE_PARAMS_JSON="${CEQ_TEMPLATE_PARAMS_JSON:-{\"prompt\":\"golden path smoke\",\"width\":512,\"height\":512}}"
    fi
    run_smoke "GPU golden path" \
      CEQ_RUN_OPERATIONS_STATUS=true \
      || FAILED=1
  fi
fi

if [[ "$WRITE_EVIDENCE" == "true" ]]; then
  log "Evidence written: $EVIDENCE_FILE"
fi

if [[ "$FAILED" -ne 0 ]]; then
  log "Post-deploy verification FAILED"
  exit 1
fi

log "Post-deploy verification PASSED"
exit 0
