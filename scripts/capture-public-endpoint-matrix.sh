#!/usr/bin/env bash
# Capture a single-pass public endpoint matrix for CEQ production.
#
# Usage:
#   CEQ_EVIDENCE_FILE=ops/evidence/$(date +%F-%H%M%S)-public-endpoints.csv \
#   scripts/capture-public-endpoint-matrix.sh

set -euo pipefail

API_URL="${CEQ_API_URL:-https://api.ceq.lol}"
STUDIO_URL="${CEQ_STUDIO_URL:-https://ceq.lol}"
APP_URL="${CEQ_APP_URL:-https://app.ceq.lol}"
TIMEOUT_SECONDS="${CEQ_MATRIX_TIMEOUT_SECONDS:-12}"
EVIDENCE_DIR="${CEQ_EVIDENCE_DIR:-ops/evidence}"
EVIDENCE_FILE="${CEQ_EVIDENCE_FILE:-${EVIDENCE_DIR}/$(date -u +%Y-%m-%dT%H%M%SZ)-public-prod-endpoints.csv}"
RESOLVE_OVERRIDES="${CEQ_RESOLVE_OVERRIDES:-}"

mkdir -p "$EVIDENCE_DIR"

echo 'check,timestamp,url,final_url,status_code,location,body_snippet,headers' > "$EVIDENCE_FILE"

csv_field() {
  local value="${1:-}"
  value="${value//$'\n'/ }"
  value="${value//$'\r'/ }"
  value="${value//\"/\"\"}"
  printf '"%s"' "$value"
}

log() {
  printf '[ceq-matrix] %s\n' "$*" >&2
}

record_result() {
  local check_name="$1"
  local request_url="$2"
  local final_url="$3"
  local status_code="$4"
  local location="$5"
  local body_snippet="$6"
  local headers="$7"
  local timestamp
  timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  printf '%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$(csv_field "$check_name")" \
    "$(csv_field "$timestamp")" \
    "$(csv_field "$request_url")" \
    "$(csv_field "$final_url")" \
    "$(csv_field "$status_code")" \
    "$(csv_field "$location")" \
    "$(csv_field "$body_snippet")" \
    "$(csv_field "$headers")" >> "$EVIDENCE_FILE"
}

probe() {
  local check_name="$1"
  local method="$2"
  local url="$3"
  local payload="${4:-}"

  local response
  local curl_exit_code=0
  local body tmp_headers tmp_err
  body="$(mktemp)"
  tmp_headers="$(mktemp)"
  tmp_err="$(mktemp)"

  local curl_opts=(--silent --show-error --max-time "$TIMEOUT_SECONDS" --output "$body" --dump-header "$tmp_headers" --write-out '%{http_code} %{url_effective} %{redirect_url}')
  local -a resolve_args=()

  if [[ -n "$RESOLVE_OVERRIDES" ]]; then
    IFS=';' read -r -a resolve_args <<< "$RESOLVE_OVERRIDES"
    for resolve_entry in "${resolve_args[@]}"; do
      [[ -n "$resolve_entry" ]] || continue
      curl_opts+=(--resolve "$resolve_entry")
    done
  fi

  curl_opts+=(--connect-timeout "$TIMEOUT_SECONDS")
  curl_opts+=(-X "$method")

  if [[ -n "$payload" ]]; then
    curl_opts+=(--header 'Content-Type: application/json' --data "$payload")
  fi

  set +e
  response="$(curl "${curl_opts[@]}" "$url" 2>"$tmp_err")"
  curl_exit_code=$?
  set -e

  local status_code="curl_fail"
  local final_url="$url"
  local location=""
  local body_snippet=""
  local header_snippet=""
  local error_message=""

  if [[ "$curl_exit_code" -eq 0 ]]; then
    read -r status_code final_url location <<<"$response"
    body_snippet="$(head -c 120 "$body" | tr '\n' ' ')"
    header_snippet="$(tr -d '\r' < "$tmp_headers" | head -n 1)"

    if [[ "$status_code" == "000" ]]; then
      status_code="curl_fail"
    fi
  else
    error_message="$(head -c 200 "$tmp_err" | tr '\n' ' ')"
    status_code="curl_fail"
    body_snippet="$error_message"
    final_url="$url"
  fi

  record_result "$check_name" "$url" "$final_url" "$status_code" "$location" "$body_snippet" "$header_snippet"

  rm -f "$body" "$tmp_headers" "$tmp_err"
}

probe "API health" GET "${API_URL}/health"
probe "API ready" GET "${API_URL}/ready"
probe "API docs" GET "${API_URL}/docs"
probe "Jobs trailing slash redirect" GET "${API_URL}/v1/jobs"
probe "Jobs list no-auth" GET "${API_URL}/v1/jobs/"
probe "Templates list no-auth" GET "${API_URL}/v1/templates/?skip=0&limit=1"
probe "Templates categories" GET "${API_URL}/v1/templates/categories"
probe "Assets types" GET "${API_URL}/v1/assets/types"
probe "Outputs list" GET "${API_URL}/v1/outputs"
probe "Outputs channels" GET "${API_URL}/v1/outputs/channels"
probe "Render card no-auth" POST "${API_URL}/v1/render/card" "{}"
probe "Credits balance no-auth" GET "${API_URL}/v1/credits/balance"
probe "Operations status no-auth" GET "${API_URL}/v1/operations/status"
probe "Public landing" GET "${STUDIO_URL%/}/"
probe "App root no-cookie" GET "${APP_URL%/}/"
probe "App login" GET "${APP_URL%/}/login"
probe "App session" GET "${APP_URL%/}/api/auth/session"
probe "App docs" GET "${APP_URL%/}/api/docs"

log "Public endpoint matrix written to ${EVIDENCE_FILE}"
