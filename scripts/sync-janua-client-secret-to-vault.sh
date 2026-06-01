#!/usr/bin/env bash
# Sync JANUA_CLIENT_SECRET into Vault for CEQ ExternalSecret → ceq-janua-client-secret → Studio.
#
# Enclii-first: prefer Enclii secrets UI/CLI when available. This script is
# break-glass for operators who have Vault CLI access.
#
# NEVER commit the secret. NEVER echo it to logs.
#
# Usage:
#   # Paste secret at prompt (recommended)
#   scripts/sync-janua-client-secret-to-vault.sh
#
#   # Or pass via env for automation (ensure shell history is disabled)
#   JANUA_CLIENT_SECRET='...' scripts/sync-janua-client-secret-to-vault.sh
#
# Prerequisites:
#   - vault CLI authenticated with write access to secret/ceq
#   - GitHub repo secret JANUA_CLIENT_SECRET already set (madfam-org/ceq)

set -euo pipefail

VAULT_PATH="${CEQ_VAULT_PATH:-secret/ceq}"
PROPERTY="${CEQ_VAULT_JANUA_PROPERTY:-JANUA_CLIENT_SECRET}"

log() {
  printf '[sync-janua-vault] %s\n' "$*" >&2
}

fail() {
  printf '[sync-janua-vault] ERROR: %s\n' "$*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

need vault

if [[ -z "${JANUA_CLIENT_SECRET:-}" ]]; then
  log "Paste JANUA_CLIENT_SECRET (input hidden), then press Enter:"
  read -rs JANUA_CLIENT_SECRET
  echo >&2
fi

if [[ -z "${JANUA_CLIENT_SECRET}" ]]; then
  fail "JANUA_CLIENT_SECRET is empty"
fi

if [[ "${JANUA_CLIENT_SECRET}" == *$'\n'* ]]; then
  fail "JANUA_CLIENT_SECRET must not contain newlines"
fi

log "Verifying GitHub repo secret exists (name only)..."
if command -v gh >/dev/null 2>&1; then
  gh secret list --repo madfam-org/ceq 2>/dev/null | rg -q '^JANUA_CLIENT_SECRET' \
    || log "WARN: JANUA_CLIENT_SECRET not listed in gh secret list — continuing anyway"
else
  log "WARN: gh not installed — skipping GitHub secret presence check"
fi

log "Patching Vault ${VAULT_PATH} property ${PROPERTY}..."
if vault kv get -format=json "${VAULT_PATH}" >/dev/null 2>&1; then
  vault kv patch "${VAULT_PATH}" "${PROPERTY}=${JANUA_CLIENT_SECRET}" >/dev/null
else
  vault kv put "${VAULT_PATH}" "${PROPERTY}=${JANUA_CLIENT_SECRET}" >/dev/null
fi

unset JANUA_CLIENT_SECRET

log "Vault patch complete. Next steps:"
log "  1. kubectl -n ceq get externalsecret ceq-secrets"
log "  2. Confirm ceq-secrets has key ${PROPERTY} (check byte length only)"
log "  3. ArgoCD sync ceq-services; verify ceq-studio pods rolled"
log "  4. Browser test https://app.ceq.lol/ and docs/JANUA_OPERATOR.md §4"
