# CEQ Stability Roadmap and Remediation Plan

## Purpose

ceq is MADFAM’s internal generative-production service layer for turning prompts and workflows into deterministic, persisted outputs across social/video/3D modalities.

It combines:

- `ceq-studio` (Next.js) for execution UX, output gallery, and queue monitor
- `ceq-api` (FastAPI) for auth, workflow orchestration, persistence, and job/outputs APIs
- `ceq-workers` for GPU execution + ComfyUI + output upload pipeline
- Kubernetes + Enclii for shared infra (Redis, PostgreSQL, ingress, autoscaling)

## Mission

Make CEQ a stable production execution primitive: job dispatch and completion must be reliably persisted, queryable, and replayable while keeping user experience fast and predictable.

## Vision

Run CEQ as a deterministic, observable system:

- Jobs are submitted once and tracked end-to-end
- Completion always updates both Redis (real-time) and PostgreSQL (durable)
- Output metadata/schema is consistent across DB, API responses, and callbacks
- Remediation actions are documented as code-backed, test-covered change sets

## Current Status Snapshot (2026-05-14)

### What is working

- Service topology and production deployment paths are present.
- Core APIs are reachable in production; render pipelines (card/audio/3D) are functional.
- DB, Redis, R2, Janua, and CI scaffolding are in place.

### Closed instability surfaces in this stabilization pass

1. **API/worker contract mismatch**
   - Output APIs now use the current `Output` model fields (`filename`, `file_type`, `file_size_bytes`, `preview_url`, `output_metadata`).
   - `jobs.py` cancellation now removes current and legacy queued payload shapes.
   - `synthesis.py` no longer reads missing `Template.slug` / `Template.is_deleted` fields and creates an ephemeral workflow before creating a job.

2. **Worker completion persistence gap**
   - Worker completion now posts a token-protected callback to the API.
   - PostgreSQL job status and output rows are persisted from worker results; Redis remains the real-time status path.

3. **Migration drift**
   - A follow-up Alembic revision aligns the `outputs` table with the live model contract.

4. **Schema drift risk in API responses**
   - `jobs`, `outputs`, worker callback payloads, and Studio gallery consumers now share the modern output shape.

5. **Worker image-name drift**
   - Worker defaults, Vast/Furnace provider defaults, and Vast deployment docs now use the production dash-form image name: `ghcr.io/madfam-org/ceq-worker`.

### Remediation status in this change set

- P1 runtime contract fixes are implemented for DB session access, synthesis workflow creation, queue cancellation, output API shape, and worker completion persistence.
- P2 schema/config/infra alignment is implemented with a dedicated Alembic migration, callback token settings, R2 bucket env alias support, Kubernetes worker/API env wiring, and dash-form worker image defaults.
- P3 regression coverage is added for callback persistence/idempotency/auth, cancel queue removal, modern output registration/listing, worker upload descriptors, and worker callback posting.
- Verification completed locally:
  - `apps/api`: `291 passed, 1 skipped`
  - `apps/workers`: `109 passed`
  - `apps/studio`: typecheck passed; `71 passed`
  - Alembic has one head: `20260513_align_outputs`

## Remaining Roadmap To Full Stability

The items below are what remains after the current stabilization patch. They are ordered by production risk and should be treated as the next execution plan.

### P0 — Production Rollout Gates

1. **Provision the callback secret**
   - Add `JOB_COMPLETION_CALLBACK_TOKEN` to production `ceq-secrets`.
   - The API requires this in production; workers use the same value when POSTing completion reports.

2. **Run and verify migrations**
   - Apply Alembic head through the GitOps migration job.
   - Confirm existing `outputs` rows have non-null `filename`, `file_type`, and `file_size_bytes`.

3. **Run a real end-to-end GPU smoke**
   - Studio/API job submission -> Redis pending queue -> worker execution -> R2 upload -> API callback -> PostgreSQL output row -> Studio gallery render.
   - Acceptance: the final job is `completed`, output rows are durable, and gallery URLs open from the browser.

4. **Verify network policy paths**
   - Worker -> `ceq-api` callback path.
   - Worker/API -> Redis DB 14.
   - Worker/API -> Cloudflare R2.

5. **Verify Janua production client**
   - Confirm Janua knows the active CEQ client ID and redirect URIs.
   - Acceptance: production Studio login succeeds and websocket auth token can be used for job streams.

### P1 — Remaining Functional Correctness

1. **Fix Studio request and websocket contracts**
   - `runWorkflow()` / `runTemplate()` currently pass `input_params`; API routers expect `params`.
   - `subscribeToJob()` must append the auth token because `/v1/jobs/{job_id}/stream` requires `?token=...`.

2. **Implement user-provided job webhooks**
   - `webhook_url` is accepted and stored today, but completion delivery to that URL is not yet implemented.
   - Add signed delivery, retry, and failure metadata.

3. **Implement active worker cancellation**
   - API publishes a cancel control message, but workers need to subscribe per active job and interrupt ComfyUI execution.
   - Acceptance: cancelling a running job stops GPU work and persists `cancelled`.

4. **Broaden worker output collection**
   - Current ComfyUI output collection is image-oriented.
   - Add video/audio/3D/arbitrary file collection, MIME mapping, dimensions/duration extraction, and tests.

### P2 — Reliability Hardening

1. **Add callback retry and dead-letter handling**
   - Failed worker -> API callbacks should retry with backoff.
   - Exhausted callbacks should land in an inspectable dead-letter queue.

2. **Add DB-level idempotency**
   - Add a unique constraint for `(job_id, storage_uri)` after live data is checked for duplicates.
   - Keep the app-level idempotency already added.

3. **Add production-grade migration tests**
   - Add PostgreSQL-backed migration tests for legacy output rows.
   - SQLite model tests are not enough for JSONB/constraint behavior.

4. **Pin worker images by digest**
   - `ceq-worker:latest` remains a rollout reproducibility risk.
   - Update CI/GitOps to publish and pin worker digests like API and Studio.

### P3 — Observability And Product Completion

1. **Add alerts and dashboards**
   - Queue depth, stuck running jobs, callback failures, R2 upload failures, GPU worker health, migration failures.

2. **Finalize monetization path**
   - Replace InterestGate with checkout/tier enforcement once pricing and billing are locked.

3. **Complete publishing channels**
   - Twitter/X, Instagram, LinkedIn, and Discord remain `coming_soon`; webhook is the only implemented publishing channel.

4. **Secret hygiene**
   - Move production secrets fully to sealed/external secrets.
   - Rotate any real-looking credentials left in operator-local examples.

## Completed Remediation Plan

The team requested an implementation plan in **priority order** and explicit parallel work where safe. The order below is the remediation sequence executed in this stabilization pass:

1. Fixed immediate runtime blockers first (P1), so existing services stop failing fast.
2. Closed data-contract gaps (P2), so remaining behavior becomes deterministic.
3. Added hardening and test coverage (P3), so regression risk is reduced.

All P1 changes were independent from infra wiring. P2 infra edits are additive and should be rolled out behind the production gates listed above.

## Completed Workstreams

### Roadmap Execution Strategy

- **Documented**: every implementation has a corresponding acceptance entry below.
- **P1, then P2, then P3**: later-phase changes did not mask earlier blockers.
- **Parallelized P3**: tests and docs updates were added around the stabilized contracts.

### P1 — Runtime Contract Correctness (completed)

1. **Export writable DB session factory alias used by websocket/job path** — completed
   - File: `apps/api/src/ceq_api/db/session.py`
   - Add `async_session_maker` compatibility export and wire through `apps/api/src/ceq_api/db/__init__.py`.
   - Keep behavior safe under startup lifecycle used by current sessions.

2. **Fix broken synthesis template resolution** — completed
   - File: `apps/api/src/ceq_api/routers/synthesis.py`
   - Stop using nonexistent `Template.slug` and `Template.is_deleted`.
   - Resolve by existing `Template` schema (`name`/`category` + `workflow_json`) with deterministic fallback.

3. **Fix queue cancellation payload mismatch** — completed
   - File: `apps/api/src/ceq_api/routers/jobs.py`
   - Remove pending jobs using `{"id": str(job_id)}` and not legacy `{"job_id": ...}`.

4. **Modernize output API contract** — completed
   - File: `apps/api/src/ceq_api/routers/outputs.py`
   - Align request/response fields to `Output` model fields.
   - Ensure publish/delete/list paths use modern field names.

5. **Add worker→API completion callback** — completed
   - File: `apps/api/src/ceq_api/routers/jobs.py`
   - Add internal endpoint (token-protected) to persist final job status + outputs.

6. **Update worker execution return payload and callback behavior** — completed
   - Files: `apps/workers/src/ceq_worker/handler.py`, `apps/workers/src/ceq_worker/queue.py`
   - Build per-output descriptors with size/type metadata.
   - POST completion payload to API callback endpoint.
   - Keep Redis fallback writes as non-fatal backstop.

7. **Add idempotent worker→API completion endpoint contract tests** — completed
   - File: `apps/api/tests/test_jobs.py`
   - Add regression test for authenticated callback updates and a malformed payload guard.

### P1 Completion Criteria (met locally)

- `POST /v1/jobs/{job_id}/outputs/report` accepts a callback payload and persists job status + outputs.
- Cancel endpoint removes pending queue items for both `{"id":...}` and legacy `{"job_id":...}` payloads.
- `jobs` and `synthesis` routes no longer access non-existent model fields.
- `outputs` list/register are compatible with current `Output` model.

### Why this order

- P1 item 1 enables worker and script code paths that already import `async_session_maker`.
- P1 item 2, 3, and 4 eliminate runtime exceptions in production endpoints.
- P1 item 5 and 6 ensure finalization is not best-effort-only anymore.

### P2 — Data/Schema Consistency (completed)

1. **Create Alembic migration to align `outputs` table** — completed
   - File: `apps/api/src/ceq_api/alembic/versions/...`
   - Transition legacy columns to modern contract without data-loss of existing rows.

2. **Add worker/API settings for callback path + auth** — completed
   - Files: `apps/api/src/ceq_api/config.py`, `apps/workers/src/ceq_worker/config.py`, `infrastructure/k8s/*`
   - Add configurable `API_URL`, callback path, and shared callback token.

3. **Update infra docs + manifests** — completed
   - Files: `infrastructure/k8s/worker-deployment.yaml`, secrets/config docs where needed
   - Ensure callback env + secret token are present in runtime config.

### P3 — Reliability and Observability (completed locally)

1. **Fallback behavior hardening** — completed
   - Keep Redis result writes for continuity when callback fails.
   - Mark transient callback failure without dropping worker execution status.

2. **Add regression tests for end-to-end contract edges** — completed
   - Files: `apps/api/tests/*`, `apps/workers/tests/*`
   - Add targeted tests for output contract, completion callback, queue-cancel payload correctness.

### P3 Completion Criteria (met locally)

- Job completion callback has negative-path test cases (invalid signature, unknown job, partial payload).
- Queue cancel compatibility with stale queue shapes is covered by tests.
- Output contract compatibility test includes both `file_type` filter and `storage_uri` payload shape.
- Migration regression test validates new outputs columns can be read and written end-to-end in tests using SQLite models.

## Service Scope and Parallelization Record

The table below records ownership for the completed remediation and the next recommended parallel work.

- **api-core** (`apps/api/src/ceq_api`)
  - `db/session.py`, `db/__init__.py`, `routers/synthesis.py`, `routers/jobs.py`, `routers/outputs.py`, `config.py`
  - Completed runtime contracts, callback endpoint, output persistence, and API settings.
  - Next: user webhook delivery, stronger callback observability, and active-cancel persistence support.

- **worker** (`apps/workers/src/ceq_worker`)
  - `handler.py`, `queue.py`, `storage.py`, `config.py`
  - Completed execution payloads, R2 descriptors, callback posting, and Redis fallback writes.
  - Next: retry/dead-letter handling, active cancellation, and broader non-image output collection.

- **data**
  - `apps/api/src/ceq_api/alembic/versions/*`
  - Completed outputs schema alignment.
  - Next: live duplicate audit, DB-level `(job_id, storage_uri)` idempotency, and PostgreSQL-backed migration tests.

- **infra** (`infrastructure/k8s/*`)
  - `worker-deployment.yaml`, `secrets.yaml`
  - Completed callback token wiring and R2 env alias wiring.
  - Next: provision production token, verify NetworkPolicies, and pin worker images by digest.

- **frontend** (`apps/studio/src`)
  - Completed gallery URL consumption through `public_url` fallback.
  - Next: workflow/template submit payload alignment and websocket token handling.

## Risk Register (short and explicit)

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Callback path added but token not provisioned in staging/prod first | Callback requests rejected, queue fallback still works | Keep Redis fallback; expose non-fatal logs and mark callback failures in `job.error` metadata |
| Alembic migration run in environments with pre-existing output rows | Possible migration constraint errors | Migration copies legacy data to new columns with defaults and keeps old `published_to`/`output_metadata` shape |
| Template fallback logic in synthesis selects wrong template | Suboptimal GPU routing | Choose by `category='3d'`, with deterministic fallback by name substring and tags; record `output_error` if none found |

## Known debt (deferred to next milestone)

- Remaining debt is now tracked in **Remaining Roadmap To Full Stability** above.
- Do not add new stability work without assigning it to a P0/P1/P2/P3 bucket.

## Files Changed By Scope

- **apps/api**
  - `db.session`, `routers.jobs`, `routers.synthesis`, `routers.outputs`, `config`
  - Added callback endpoint, contract fixes, token checks, output persistence, and migration coverage.

- **apps/workers**
  - `handler.py`, `queue.py`, `storage.py`, `config.py`, `comfyui.py`, `orchestrator.py`
  - Built rich output descriptors, sent callbacks with auth, awaited async progress callbacks, and kept Redis fallback writes.

- **infrastructure/k8s**
  - `api-deployment.yaml`, `worker-deployment.yaml`, `secrets.yaml`
  - Wired callback env vars, token secret, API callback URL, and R2 bucket alias.

- **apps/studio**
  - `src/lib/api.ts`, gallery components
  - Consumes `public_url` where available and preserves `storage_uri` fallback behavior.

- **docs/tests**
  - `docs/CEQ_STABILITY_ROADMAP.md`, `tests/*`
  - Documents remediation and keeps tests in sync with contracts.

## Completed Acceptance Criteria

- `/v1/jobs/{id}/cancel` reliably removes queued payload from Redis with the actual queued shape.
- `/v1/outputs` and `/v1/jobs/{id}/outputs` consistently use `Output` model fields.
- Worker completions persist final `Job` status and durable `Output` rows.
- `apps/api` migration chain has a committed revision that aligns `outputs` schema.
- Callback endpoint accepts worker completion payload and authenticates via shared token.
- CI includes regression for at least:
  - synthesis template fallback logic
  - queue cancel payload
  - callback persistence idempotency
  - modern output response fields
