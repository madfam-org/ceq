#!/usr/bin/env bash
# CEQ production smoke check.
#
# Public checks need no credentials. The full production proof requires:
#   CEQ_AUTH_TOKEN=<Janua JWT>
#   CEQ_TEMPLATE_ID=<template UUID>
# Optional:
#   CEQ_TEMPLATE_PARAMS_JSON='{"prompt":"..."}'
#   CEQ_PUBLIC_ONLY=true

set -euo pipefail

API_URL="${CEQ_API_URL:-https://api.ceq.lol}"
STUDIO_URL="${CEQ_STUDIO_URL:-https://ceq.lol}"
AUTH_TOKEN="${CEQ_AUTH_TOKEN:-}"
TEMPLATE_ID="${CEQ_TEMPLATE_ID:-}"
TEMPLATE_PARAMS_JSON="${CEQ_TEMPLATE_PARAMS_JSON:-{}}"
PUBLIC_ONLY="${CEQ_PUBLIC_ONLY:-false}"
POLL_TIMEOUT_SECONDS="${CEQ_POLL_TIMEOUT_SECONDS:-600}"
POLL_INTERVAL_SECONDS="${CEQ_POLL_INTERVAL_SECONDS:-5}"
EXPECT_OUTPUTS="${CEQ_EXPECT_OUTPUTS:-true}"

log() {
  printf '[ceq-smoke] %s\n' "$*"
}

fail() {
  printf '[ceq-smoke] ERROR: %s\n' "$*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

curl_json() {
  local method="$1"
  local url="$2"
  local data="${3:-}"

  if [[ -n "$data" ]]; then
    curl --fail --silent --show-error \
      --request "$method" \
      --header "Authorization: Bearer ${AUTH_TOKEN}" \
      --header "Content-Type: application/json" \
      --data "$data" \
      "$url"
  elif [[ -n "$AUTH_TOKEN" ]]; then
    curl --fail --silent --show-error \
      --request "$method" \
      --header "Authorization: Bearer ${AUTH_TOKEN}" \
      "$url"
  else
    curl --fail --silent --show-error --request "$method" "$url"
  fi
}

http_status() {
  curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$1"
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
[[ -n "$TEMPLATE_ID" ]] || fail "Set CEQ_TEMPLATE_ID to run a real template job."
jq -e . >/dev/null <<<"$TEMPLATE_PARAMS_JSON" || fail "CEQ_TEMPLATE_PARAMS_JSON is not valid JSON."

log "Verifying template ${TEMPLATE_ID}"
curl_json GET "${API_URL}/v1/templates/${TEMPLATE_ID}" >/dev/null

run_payload="$(jq -n --argjson params "$TEMPLATE_PARAMS_JSON" '{params: $params, priority: 0}')"
log "Submitting template job"
run_response="$(curl_json POST "${API_URL}/v1/templates/${TEMPLATE_ID}/run" "$run_payload")"
job_id="$(jq -r '.job_id // empty' <<<"$run_response")"
[[ -n "$job_id" ]] || fail "Template run did not return job_id: ${run_response}"
log "Queued job ${job_id}"

deadline=$((SECONDS + POLL_TIMEOUT_SECONDS))
job_json=""

while (( SECONDS < deadline )); do
  job_json="$(curl_json GET "${API_URL}/v1/jobs/${job_id}")"
  job_status="$(jq -r '.status // empty' <<<"$job_json")"
  progress="$(jq -r '.progress // 0' <<<"$job_json")"
  log "Job ${job_id}: status=${job_status} progress=${progress}"

  case "$job_status" in
    completed)
      break
      ;;
    failed|cancelled)
      fail "Job ended with status=${job_status}: $(jq -c '{error, outputs}' <<<"$job_json")"
      ;;
  esac

  sleep "$POLL_INTERVAL_SECONDS"
done

final_status="$(jq -r '.status // empty' <<<"$job_json")"
[[ "$final_status" == "completed" ]] || fail "Timed out waiting for job completion."

outputs_json="$(curl_json GET "${API_URL}/v1/jobs/${job_id}/outputs")"
outputs_count="$(jq 'length' <<<"$outputs_json")"

if [[ "$EXPECT_OUTPUTS" == "true" && "$outputs_count" -lt 1 ]]; then
  fail "Job completed but /v1/jobs/${job_id}/outputs returned no outputs."
fi

if [[ "$outputs_count" -gt 0 ]]; then
  durable_count="$(jq '[.[] | select((.storage_uri // "") != "" and (.filename // "") != "" and (.file_type // "") != "")] | length' <<<"$outputs_json")"
  url_count="$(jq '[.[] | select((.public_url // .preview_url // .storage_uri // "") != "")] | length' <<<"$outputs_json")"
  [[ "$durable_count" -eq "$outputs_count" ]] || fail "One or more outputs are missing durable metadata."
  [[ "$url_count" -eq "$outputs_count" ]] || fail "One or more outputs are missing browser/gallery URL data."
fi

gallery_json="$(curl_json GET "${API_URL}/v1/outputs/?job_id=${job_id}&limit=10")"
gallery_count="$(jq '.outputs | length' <<<"$gallery_json")"

if [[ "$EXPECT_OUTPUTS" == "true" && "$gallery_count" -lt 1 ]]; then
  fail "Gallery output list did not include outputs for job ${job_id}."
fi

log "Full production smoke passed for job ${job_id}; outputs=${outputs_count}."
