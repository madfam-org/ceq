#!/usr/bin/env bash
# CEQ production smoke check.
#
# Public checks need no credentials. Full runtime proof uses public APIs only:
#   CEQ_AUTH_TOKEN=<Janua JWT>
#   CEQ_TEMPLATE_ID=<template UUID>
#
# Optional gates:
#   CEQ_RUN_OPERATIONS_STATUS=true CEQ_ADMIN_AUTH_TOKEN=<admin Janua JWT>
#   CEQ_TEMPLATE_SMOKES_JSON='[{"label":"image","template_id":"...","params":{}}]'
#   CEQ_RUN_CANCEL_SMOKE=true CEQ_CANCEL_TEMPLATE_ID=<long-running template UUID>
#   CEQ_PUBLIC_ONLY=true

set -euo pipefail

API_URL="${CEQ_API_URL:-https://api.ceq.lol}"
STUDIO_URL="${CEQ_STUDIO_URL:-https://ceq.lol}"
AUTH_TOKEN="${CEQ_AUTH_TOKEN:-}"
ADMIN_AUTH_TOKEN="${CEQ_ADMIN_AUTH_TOKEN:-$AUTH_TOKEN}"
TEMPLATE_ID="${CEQ_TEMPLATE_ID:-}"
TEMPLATE_PARAMS_JSON="${CEQ_TEMPLATE_PARAMS_JSON:-{}}"
TEMPLATE_SMOKES_JSON="${CEQ_TEMPLATE_SMOKES_JSON:-}"
PUBLIC_ONLY="${CEQ_PUBLIC_ONLY:-false}"
POLL_TIMEOUT_SECONDS="${CEQ_POLL_TIMEOUT_SECONDS:-600}"
POLL_INTERVAL_SECONDS="${CEQ_POLL_INTERVAL_SECONDS:-5}"
EXPECT_OUTPUTS="${CEQ_EXPECT_OUTPUTS:-true}"
RUN_OPERATIONS_STATUS="${CEQ_RUN_OPERATIONS_STATUS:-false}"
REQUIRE_OPERATIONS_STATUS="${CEQ_REQUIRE_OPERATIONS_STATUS:-false}"
RUN_CANCEL_SMOKE="${CEQ_RUN_CANCEL_SMOKE:-false}"
CANCEL_TEMPLATE_ID="${CEQ_CANCEL_TEMPLATE_ID:-$TEMPLATE_ID}"
CANCEL_TEMPLATE_PARAMS_JSON="${CEQ_CANCEL_TEMPLATE_PARAMS_JSON:-$TEMPLATE_PARAMS_JSON}"
CANCEL_AFTER_SECONDS="${CEQ_CANCEL_AFTER_SECONDS:-10}"

log() {
  printf '[ceq-smoke] %s\n' "$*" >&2
}

fail() {
  printf '[ceq-smoke] ERROR: %s\n' "$*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

curl_json_with_token() {
  local token="$1"
  local method="$2"
  local url="$3"
  local data="${4:-}"
  local args=(--fail --silent --show-error --request "$method")

  if [[ -n "$token" ]]; then
    args+=(--header "Authorization: Bearer ${token}")
  fi
  if [[ -n "$data" ]]; then
    args+=(--header "Content-Type: application/json" --data "$data")
  fi

  curl "${args[@]}" "$url"
}

curl_json() {
  curl_json_with_token "$AUTH_TOKEN" "$@"
}

http_status() {
  curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$1"
}

assert_json() {
  local name="$1"
  local value="$2"
  jq -e . >/dev/null <<<"$value" || fail "${name} is not valid JSON."
}

run_operations_status() {
  if [[ "$RUN_OPERATIONS_STATUS" != "true" && "$REQUIRE_OPERATIONS_STATUS" != "true" ]]; then
    return
  fi

  if [[ -z "$ADMIN_AUTH_TOKEN" ]]; then
    if [[ "$REQUIRE_OPERATIONS_STATUS" == "true" ]]; then
      fail "Set CEQ_ADMIN_AUTH_TOKEN to require operations status checks."
    fi
    log "Skipping operations status; set CEQ_RUN_OPERATIONS_STATUS=true and CEQ_ADMIN_AUTH_TOKEN to enable."
    return
  fi

  log "Checking admin operations status"
  local operations_json
  local callback_configured
  local redis_reachable
  local revision
  local dead_letters
  operations_json="$(curl_json_with_token "$ADMIN_AUTH_TOKEN" GET "${API_URL}/v1/operations/status")"
  callback_configured="$(jq -r '.callback_token_configured' <<<"$operations_json")"
  redis_reachable="$(jq -r '.redis.reachable' <<<"$operations_json")"
  revision="$(jq -r '.alembic_revision // "unknown"' <<<"$operations_json")"
  dead_letters="$(jq -r '.redis.completion_dead_letters // "unknown"' <<<"$operations_json")"

  [[ "$callback_configured" == "true" ]] || fail "Worker callback token is not configured in operations status."
  [[ "$redis_reachable" == "true" ]] || fail "Redis is not reachable in operations status."

  log "Operations status ok: alembic=${revision} completion_dead_letters=${dead_letters}"
}

submit_template_job() {
  local label="$1"
  local template_id="$2"
  local params_json="$3"

  [[ -n "$template_id" ]] || fail "Template smoke '${label}' is missing template_id."
  assert_json "params for ${label}" "$params_json"

  log "Verifying template ${label} (${template_id})"
  curl_json GET "${API_URL}/v1/templates/${template_id}" >/dev/null

  local run_payload
  local run_response
  local job_id
  run_payload="$(jq -n --argjson params "$params_json" '{params: $params, priority: 0}')"
  log "Submitting ${label} template job"
  run_response="$(curl_json POST "${API_URL}/v1/templates/${template_id}/run" "$run_payload")"
  job_id="$(jq -r '.job_id // empty' <<<"$run_response")"
  [[ -n "$job_id" ]] || fail "Template run did not return job_id: ${run_response}"
  printf '%s' "$job_id"
}

poll_for_completion() {
  local label="$1"
  local job_id="$2"
  local deadline=$((SECONDS + POLL_TIMEOUT_SECONDS))
  local job_json=""
  local job_status=""
  local progress=""

  while (( SECONDS < deadline )); do
    job_json="$(curl_json GET "${API_URL}/v1/jobs/${job_id}")"
    job_status="$(jq -r '.status // empty' <<<"$job_json")"
    progress="$(jq -r '.progress // 0' <<<"$job_json")"
    log "${label} job ${job_id}: status=${job_status} progress=${progress}"

    case "$job_status" in
      completed)
        printf '%s' "$job_json"
        return
        ;;
      failed|cancelled)
        fail "${label} job ended with status=${job_status}: $(jq -c '{error, outputs, output_metadata}' <<<"$job_json")"
        ;;
    esac

    sleep "$POLL_INTERVAL_SECONDS"
  done

  fail "Timed out waiting for ${label} job ${job_id} completion."
}

verify_outputs() {
  local label="$1"
  local job_id="$2"
  local expect_outputs="$3"
  local outputs_json
  local outputs_count
  local durable_count
  local url_count
  local gallery_json
  local gallery_count

  outputs_json="$(curl_json GET "${API_URL}/v1/jobs/${job_id}/outputs")"
  outputs_count="$(jq 'length' <<<"$outputs_json")"

  if [[ "$expect_outputs" == "true" && "$outputs_count" -lt 1 ]]; then
    fail "${label} job completed but /v1/jobs/${job_id}/outputs returned no outputs."
  fi

  if [[ "$outputs_count" -gt 0 ]]; then
    durable_count="$(jq '[.[] | select((.storage_uri // "") != "" and (.filename // "") != "" and (.file_type // "") != "")] | length' <<<"$outputs_json")"
    url_count="$(jq '[.[] | select((.public_url // .preview_url // .storage_uri // "") != "")] | length' <<<"$outputs_json")"
    [[ "$durable_count" -eq "$outputs_count" ]] || fail "${label} output metadata is incomplete."
    [[ "$url_count" -eq "$outputs_count" ]] || fail "${label} output browser/gallery URL data is incomplete."
  fi

  gallery_json="$(curl_json GET "${API_URL}/v1/outputs/?job_id=${job_id}&limit=10")"
  gallery_count="$(jq '.outputs | length' <<<"$gallery_json")"

  if [[ "$expect_outputs" == "true" && "$gallery_count" -lt 1 ]]; then
    fail "Gallery output list did not include outputs for ${label} job ${job_id}."
  fi

  log "${label} smoke passed for job ${job_id}; outputs=${outputs_count}."
}

run_template_smoke() {
  local label="$1"
  local template_id="$2"
  local params_json="$3"
  local expect_outputs="$4"
  local job_id

  job_id="$(submit_template_job "$label" "$template_id" "$params_json")"
  poll_for_completion "$label" "$job_id" >/dev/null
  verify_outputs "$label" "$job_id" "$expect_outputs"
}

run_template_smokes() {
  if [[ -n "$TEMPLATE_SMOKES_JSON" ]]; then
    assert_json "CEQ_TEMPLATE_SMOKES_JSON" "$TEMPLATE_SMOKES_JSON"
    jq -e 'type == "array" and all(.[]; (.template_id // "") != "")' >/dev/null <<<"$TEMPLATE_SMOKES_JSON" \
      || fail "CEQ_TEMPLATE_SMOKES_JSON must be an array of objects with template_id."

    while IFS= read -r smoke; do
      local label
      local template_id
      local params_json
      local expect_outputs
      label="$(jq -r '.label // .template_id' <<<"$smoke")"
      template_id="$(jq -r '.template_id' <<<"$smoke")"
      params_json="$(jq -c '.params // {}' <<<"$smoke")"
      expect_outputs="$(jq -r '.expect_outputs // empty' <<<"$smoke")"
      [[ -n "$expect_outputs" ]] || expect_outputs="$EXPECT_OUTPUTS"
      run_template_smoke "$label" "$template_id" "$params_json" "$expect_outputs"
    done < <(jq -c '.[]' <<<"$TEMPLATE_SMOKES_JSON")
    return
  fi

  [[ -n "$TEMPLATE_ID" ]] || fail "Set CEQ_TEMPLATE_ID or CEQ_TEMPLATE_SMOKES_JSON to run authenticated production smoke."
  run_template_smoke "primary" "$TEMPLATE_ID" "$TEMPLATE_PARAMS_JSON" "$EXPECT_OUTPUTS"
}

run_cancel_smoke() {
  if [[ "$RUN_CANCEL_SMOKE" != "true" ]]; then
    return
  fi

  [[ -n "$CANCEL_TEMPLATE_ID" ]] || fail "Set CEQ_CANCEL_TEMPLATE_ID or CEQ_TEMPLATE_ID to run cancel smoke."
  assert_json "CEQ_CANCEL_TEMPLATE_PARAMS_JSON" "$CANCEL_TEMPLATE_PARAMS_JSON"

  local job_id
  job_id="$(submit_template_job "cancel" "$CANCEL_TEMPLATE_ID" "$CANCEL_TEMPLATE_PARAMS_JSON")"
  log "Queued cancel smoke job ${job_id}; waiting ${CANCEL_AFTER_SECONDS}s before DELETE"
  sleep "$CANCEL_AFTER_SECONDS"

  curl_json DELETE "${API_URL}/v1/jobs/${job_id}" >/dev/null

  local deadline=$((SECONDS + POLL_TIMEOUT_SECONDS))
  local job_json=""
  local job_status=""
  local cancel_mark=""
  while (( SECONDS < deadline )); do
    job_json="$(curl_json GET "${API_URL}/v1/jobs/${job_id}")"
    job_status="$(jq -r '.status // empty' <<<"$job_json")"
    log "cancel job ${job_id}: status=${job_status}"
    case "$job_status" in
      cancelled)
        cancel_mark="$(jq -r '.output_metadata.cancel_requested_at // empty' <<<"$job_json")"
        [[ -n "$cancel_mark" ]] || fail "Cancelled job ${job_id} is missing cancel metadata."
        log "Cancel smoke passed for job ${job_id}."
        return
        ;;
      completed|failed)
        fail "Cancel smoke job reached terminal status=${job_status} before cancellation held: $(jq -c '{error, output_metadata}' <<<"$job_json")"
        ;;
    esac
    sleep "$POLL_INTERVAL_SECONDS"
  done

  fail "Timed out waiting for cancel smoke job ${job_id} to become cancelled."
}

need curl
need jq

log "Checking API health at ${API_URL}/health"
health_json="$(curl_json GET "${API_URL}/health")"
health_status="$(jq -r '.status // empty' <<<"$health_json")"
[[ -n "$health_status" ]] || fail "API health response did not include status: ${health_json}"
log "API health status: ${health_status}"

log "Checking Studio at ${STUDIO_URL}"
studio_status="$(http_status "$STUDIO_URL")"
case "$studio_status" in
  200|301|302|307|308)
    log "Studio HTTP status: ${studio_status}"
    ;;
  *)
    fail "Studio returned HTTP ${studio_status}"
    ;;
esac

if [[ "$PUBLIC_ONLY" == "true" ]]; then
  log "Public-only smoke complete."
  exit 0
fi

[[ -n "$AUTH_TOKEN" ]] || fail "Set CEQ_AUTH_TOKEN to run authenticated production smoke."
assert_json "CEQ_TEMPLATE_PARAMS_JSON" "$TEMPLATE_PARAMS_JSON"

run_operations_status
run_template_smokes
run_cancel_smoke

log "Full production smoke passed."
