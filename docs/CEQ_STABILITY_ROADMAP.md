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

6. **Studio execution contract drift**
   - Studio workflow/template run calls now send `params`, matching the API routers.
   - Studio job WebSocket subscriptions now append the Janua token required by `/v1/jobs/{job_id}/stream`.

### Remediation status in this change set

- P1 runtime contract fixes are implemented for DB session access, synthesis workflow creation, queue cancellation, output API shape, and worker completion persistence.
- P2 schema/config/infra alignment is implemented with a dedicated Alembic migration, callback token settings, R2 bucket env alias support, Kubernetes worker/API env wiring, and dash-form worker image defaults.
- P3 regression coverage is added for callback persistence/idempotency/auth, cancel queue removal, modern output registration/listing, worker upload descriptors, and worker callback posting.
- Follow-up implementation wave closed the Studio request/websocket contract gap and added an API-only production smoke runner.
- Verification completed locally:
  - `apps/api`: `291 passed, 1 skipped`
  - `apps/workers`: `109 passed`
  - `apps/studio`: typecheck passed; `75 passed`
  - Alembic has one head: `20260513_align_outputs`
- Production public-edge smoke completed with `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh`:
  - `https://api.ceq.lol/health`: `ok`
  - `https://ceq.lol`: HTTP `200`
- API webhook implementation verification:
  - `apps/api`: `296 passed, 1 skipped`
- Implementation wave closed locally on 2026-05-14:
  - Active worker cancellation implemented locally across API Redis control signals, worker pub/sub, ComfyUI interrupt, and cancelled callback persistence.
  - Worker output collection broadened beyond images with image dimensions, WAV duration, MP4/MOV duration best-effort, GLB metadata, and Studio audio/video/model gallery handling.
  - Worker completion callbacks now retry retryable failures and dead-letter exhausted payloads to Redis.
  - `outputs(job_id, storage_uri)` DB-level idempotency migration added locally.
  - Deploy workflow now waits for `build-worker` when it runs so worker images can be pinned by digest during GitOps deploy commits.
- Operations acceptance wave closed locally on 2026-05-14:
  - Admin operations API added for runtime status, completion dead-letter listing, replay, and discard.
  - Job status responses now expose `output_metadata` so cancellation, webhook, and callback state is visible through normal APIs.
  - Prometheus counters added for worker completion reports, persisted outputs, cancellations, dead-letter replay outcomes, and user webhook delivery outcomes.
  - Production smoke runner now supports admin status, multi-template modality smokes, and active cancellation smokes without raw cluster/Redis access.
  - Deploy workflow now builds and signs `ceq-worker` on every deploy and requires a worker digest before committing GitOps image updates.
  - GitOps deploy run `25850545748` completed successfully and commit `44f2e0b` pinned API, Studio, and Worker by digest.
- Next-wave local verification:
  - `apps/api`: `305 passed, 2 skipped`
  - Targeted API operations/jobs/migration verification: `36 passed, 1 skipped`
  - Changed API files linted with Ruff: passed
  - `apps/workers`: `119 passed`
  - `apps/studio`: typecheck passed; `75 passed`
  - `bash -n scripts/production-smoke.sh`: passed
  - Alembic has one head: `20260514_outputs_job_storage_unique`
  - `kubectl kustomize infrastructure/k8s` rendered successfully
  - Public production smoke passed: `https://api.ceq.lol/health` ok and `https://ceq.lol` HTTP 200

## Implementation Wave 2026-05-14 Wrap-Up

This wave moved CEQ from durable completion persistence into active runtime
control and artifact-contract hardening.

### Delivered

1. **Running-job cancellation**
   - API cancellation now writes durable Redis cancellation state and publishes a per-job control command.
   - Workers watch the control channel while a job is active, cancel the handler task, interrupt ComfyUI, and report terminal `cancelled`.
   - API ignores late non-cancelled worker reports after a user cancellation, preserving the user-visible terminal state.

2. **Multi-modal output contract**
   - ComfyUI output collection now accepts image, video, audio, model, and generic file descriptors.
   - Worker storage descriptors now include richer metadata: MIME type, size, preview URL, image dimensions, WAV duration/audio data, best-effort MP4/MOV duration, and GLB header metadata.
   - Studio gallery now renders image previews, video playback, audio playback, model categorization, and generic files.

3. **Completion callback reliability**
   - Worker -> API completion callbacks retry retryable failures with configurable backoff.
   - Exhausted completion callback payloads are retained in Redis `ceq:jobs:completion:dead`.
   - Job Redis hashes are marked with callback failure metadata for operator inspection.

4. **Durable idempotency**
   - Added migration `20260514_outputs_job_storage_unique`.
   - Migration removes duplicate `(job_id, storage_uri)` rows before adding `uq_outputs_job_storage_uri`.
   - The app-level idempotency behavior remains in place.

5. **GitOps reproducibility**
   - Deploy workflow now includes `build-worker` in the deploy dependency graph.
   - GitOps deploy commit `44f2e0b` now pins `ceq-worker` by digest alongside API and Studio.

6. **Operations recovery surface**
   - `GET /v1/operations/status` exposes admin-only readiness signals for callback/webhook secrets, R2/auth configuration, Alembic revision, and Redis queue/dead-letter depth.
   - `GET /v1/operations/completion-dead-letters` lists exhausted worker completion callbacks from Redis.
   - `POST /v1/operations/completion-dead-letters/{index}/replay` replays one callback with `JOB_COMPLETION_CALLBACK_TOKEN` and removes the exact Redis item after success.
   - `DELETE /v1/operations/completion-dead-letters/{index}` discards handled poison payloads.

7. **Acceptance automation**
   - `scripts/production-smoke.sh` now supports `CEQ_RUN_OPERATIONS_STATUS=true`, `CEQ_TEMPLATE_SMOKES_JSON`, and `CEQ_RUN_CANCEL_SMOKE=true`.
   - The smoke path remains API-first and does not require raw Redis, pod, or cluster access.

8. **Observability hooks**
   - `/metrics` now includes CEQ application counters for worker completion reports, persisted outputs, user/API cancellations, dead-letter replay outcomes, and user webhook delivery outcomes.

9. **Worker rollout hardening**
   - Deploy workflow now builds/signs worker on every deploy, requires `WORKER_DIGEST`, and commits the worker digest alongside API and Studio.
   - Deploy run `25850545748` confirmed the first gated worker build and pushed digest commit `44f2e0b`.
   - The first cold worker build took about 26 minutes; CI/CD optimization remains a follow-up stability target.

### Local Acceptance

- API suite: `305 passed, 2 skipped`
- Targeted API operations/jobs/migration suite: `36 passed, 1 skipped`
- Changed API files Ruff lint: passed
- Worker suite: `119 passed`
- Studio suite: `75 passed`
- Studio typecheck: passed
- Smoke script syntax: passed
- Alembic heads: one head, `20260514_outputs_job_storage_unique`
- Kustomize render: passed
- Public production smoke: API health `ok`, Studio HTTP `200`

### Production Acceptance Still Required

- Provision/verify `JOB_COMPLETION_CALLBACK_TOKEN` and `JOB_WEBHOOK_SECRET` in production `ceq-secrets`.
- Let ArgoCD run the PreSync migration job and confirm `20260514_outputs_job_storage_unique` is applied.
- Run authenticated end-to-end GPU smoke through Studio/API -> Redis -> worker -> R2 -> callback -> PostgreSQL -> gallery.
- Run active-cancel smoke on a real running GPU job.
- Run video/audio/3D template smoke to prove multi-modal output handling in production.
- Monitor the next deploys for worker image build duration and digest commit consistency.

## Implementation Wave 2026-05-14 Auth + Conversion Hardening

This wave addresses the landing-vs-Studio split and the missing hard auth
boundary on `app.ceq.lol`.

### Delivered And Deployed

1. **Server-gated Studio routes**
   - `app.ceq.lol` Studio routes now require a CEQ session cookie before the
     React shell renders.
   - No-cookie app-host users are redirected to `/login?returnTo=...`.
   - Public app-host routes remain open for `/login`, `/auth/*`, and
     `/api/auth/*`.

2. **CEQ session cookie bridge**
   - OAuth token exchange now sets httpOnly access/refresh cookies.
   - Token refresh can use the httpOnly refresh cookie when local storage does
     not contain a refresh token.
   - Logout clears CEQ cookies before redirecting to Janua logout.

3. **Session bootstrap endpoint**
   - `GET /api/auth/session` returns the current user and access token from
     httpOnly cookies.
   - If the access cookie has expired and a refresh cookie exists, the endpoint
     refreshes with Janua and rotates cookies.
   - The current direct browser-to-API bearer-token client remains compatible
     while CEQ moves toward a fuller server/proxy session model.

4. **Route-level smoke coverage**
   - Public production smoke now verifies `ceq.lol` remains landing/demo only,
     `ceq.lol/login` hands off to `app.ceq.lol/login`, `app.ceq.lol/landing`
     returns to the marketing host, and no-cookie `app.ceq.lol/` is protected.

5. **Regression coverage**
   - Added tests for JWT/session helper behavior.
   - Added middleware helper tests for host split, public auth paths, session
     cookie checks, and `returnTo` login redirects.

### Local Acceptance

- `pnpm --filter @ceq/studio lint`: passed with no warnings.
- `pnpm --filter @ceq/studio typecheck`: passed.
- `pnpm --filter @ceq/studio exec vitest run`: `85 passed`.
- `pnpm --filter @ceq/studio build`: passed; existing
  `outputFileTracingRoot` Next config warning remains.
- `bash -n scripts/production-smoke.sh`: passed.
- Local middleware smoke:
  - `Host: ceq.lol /` rewrites to `/landing`.
  - `Host: ceq.lol /login` redirects to `app.ceq.lol/login`.
  - `Host: app.ceq.lol /landing` redirects to `ceq.lol/`.
  - `Host: app.ceq.lol /` without CEQ session cookies redirects to
    `/login?returnTo=%2F`.
  - `Host: app.ceq.lol /` with a refresh cookie reaches the Studio shell.
- Before this wave was deployed, production public smoke remained compatible
  with `CEQ_EXPECT_APP_AUTH_REDIRECT=false`. After deploy, the default public
  smoke must keep the unauthenticated app-gate assertion enabled.
- Live Janua check still returns `invalid_client: Unknown client_id` for
  `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk`.

### Production Acceptance

- GitOps deploy for `d2ca8b8 harden studio auth gate` completed successfully.
- Deploy-bot digest commit `1eaf6a6` was fast-forwarded locally.
- Public production smoke passed after deploy:
  `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh`
  - `https://api.ceq.lol/health`: `ok`
  - `https://ceq.lol`: HTTP `200`
  - `ceq.lol/login`: `307` to `https://app.ceq.lol/login`
  - `app.ceq.lol/landing`: `307` to `https://ceq.lol/`
  - no-cookie `app.ceq.lol/`: `307` to
    `https://app.ceq.lol/login?returnTo=%2F`

### Remaining Acceptance

- Register or rotate the Janua OAuth client so
  `https://app.ceq.lol/auth/callback` is accepted.
- Complete a browser login with real credentials and verify session bootstrap,
  refresh, logout, Studio API calls, and job WebSocket token use.
- Follow up with a deeper session migration that proxies CEQ API calls through
  the Studio server so access tokens no longer need browser storage.

### Deployment Handoff

After this wave is committed and deployed, the public-only production smoke
should run with the default auth-gate assertion enabled:

```bash
CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh
```

If that fails on the `Unauthenticated app gate` check, verify ArgoCD has rolled
the new Studio image and that `app.ceq.lol` is reaching the current pod. Do not
disable the assertion after rollout except for a documented rollback.

## Next Implementation Wave Plan — Production Auth Acceptance + Full Runtime Proof

This is the active remediation and implementation plan across the relevant CEQ
services. The work should run in parallel where ownership is independent, but
acceptance must stay ordered so CEQ does not declare stability before the user
journey and GPU runtime are proven end to end.

### Lane 1 — Identity And Studio Session

Owner surface: Janua operator config, `apps/studio`, `api.ceq.lol` auth usage.

1. **Register or rotate the Janua OAuth client**
   - Required redirect URI: `https://app.ceq.lol/auth/callback`.
   - Keep `http://localhost:5801/auth/callback` for development.
   - Update `NEXT_PUBLIC_JANUA_CLIENT_ID` and `JANUA_CLIENT_SECRET` if the
     client ID rotates.
   - Acceptance: Janua no longer returns `invalid_client` for the CEQ client.

2. **Browser-prove the deployed session flow**
   - Visit no-cookie `https://app.ceq.lol/`.
   - Confirm redirect to `app.ceq.lol/login`, then Janua.
   - Complete credential login.
   - Confirm `/auth/callback` sets CEQ session cookies.
   - Confirm `/api/auth/session` bootstraps the Studio browser state.
   - Confirm refresh and logout clear/rotate cookies correctly.

3. **Migrate Studio API access behind a BFF/proxy**
   - Add same-origin Studio server routes for CEQ API calls.
   - Server reads httpOnly CEQ session cookies and attaches Janua bearer tokens
     to `api.ceq.lol`.
   - Remove or sharply reduce browser `localStorage` token dependency.
   - Acceptance: reloads and protected route navigation work without readable
     browser bearer-token storage.

4. **Add browser E2E auth tests**
   - Cover unauthenticated app redirect, marketing/app host split, callback
     success/failure, refresh, logout, and authenticated Studio shell.
   - Acceptance: Playwright suite runs locally and in CI for auth-critical
     routes with deterministic mocked Janua responses, plus a documented manual
     live-auth smoke for production.

### Lane 2 — API, Worker, And Data Runtime Proof

Owner surface: `apps/api`, `apps/workers`, Redis DB 14, PostgreSQL, R2.

1. **Provision and verify runtime secrets**
   - `JOB_COMPLETION_CALLBACK_TOKEN`
   - `JOB_WEBHOOK_SECRET`
   - Acceptance: admin `GET /v1/operations/status` reports callback/webhook
     readiness without raw pod or secret access.

2. **Verify migration and data contract in production**
   - Confirm Alembic head includes `20260514_outputs_job_storage_unique`.
   - Confirm `outputs(job_id, storage_uri)` uniqueness exists.
   - Confirm current output rows expose `filename`, `file_type`,
     `file_size_bytes`, `preview_url`, and `output_metadata`.
   - Acceptance: operations status plus authenticated output API reads prove the
     active runtime contract.

3. **Run authenticated GPU smoke**
   - `scripts/production-smoke.sh` with `CEQ_AUTH_TOKEN`, `CEQ_TEMPLATE_ID`,
     `CEQ_RUN_OPERATIONS_STATUS=true`, and `CEQ_ADMIN_AUTH_TOKEN`.
   - Acceptance: Studio/API submission reaches Redis, worker executes, R2
     upload succeeds, callback persists PostgreSQL rows, and Studio gallery can
     open the output URLs.

4. **Run active cancellation smoke**
   - Use `CEQ_RUN_CANCEL_SMOKE=true` and a long-running template.
   - Acceptance: worker interrupts ComfyUI, API remains `cancelled`, and late
     success reports cannot overwrite the terminal state.

5. **Run multi-modal artifact smoke**
   - Use `CEQ_TEMPLATE_SMOKES_JSON` for image, video, audio, and 3D/model
     templates.
   - Acceptance: each artifact persists with correct MIME/metadata and renders
     or opens from Studio gallery.

### Lane 3 — Operations, Observability, And CI/CD

Owner surface: `.github/workflows`, `scripts/`, Enclii observability,
Prometheus/alerts.

1. **Wire alerts and dashboards**
   - Queue depth, stuck running jobs, callback dead letters, R2 upload failures,
     worker health, migration failures, and OAuth error rate.
   - Acceptance: each critical failure mode has a dashboard panel and alert
     threshold.

2. **Harden production smoke automation**
   - Keep public smoke as the unauthenticated edge gate.
   - Add a browser smoke entrypoint for auth/session behavior.
   - Keep authenticated GPU/cancel/multi-modal smokes API-first and
     Enclii-first.
   - Acceptance: CI/manual runbooks tell operators which smoke to run for each
     deployment or incident.

3. **Clean CI/CD debt**
   - [x] Fix the existing Next `outputFileTracingRoot` warning by moving it under
     `experimental` in `apps/studio/next.config.mjs`.
   - [x] Update GitHub Actions away from Node 20; CI now uses Node 24.
   - Investigate deploy/notify queue delays.
   - Investigate deploy/notify queue delays.
   - Acceptance: Studio build has no config warnings and deploy workflows do
     not rely on deprecated action runtimes.

### Lane 4 — Landing, Demo, And Conversion

Owner surface: `ceq.lol` landing/demo, `apps/studio/src/components/landing`,
PMF/InterestGate telemetry.

1. **Make the landing host conversion-complete**
   - `ceq.lol` remains public landing/demo only.
   - Add a self-contained demo that shows CEQ value without entering Studio.
   - Route all product-use CTAs to `https://app.ceq.lol/login`.
   - Acceptance: no Studio shell leaks onto `ceq.lol`, and CTAs preserve the
     intended return path.

2. **Instrument funnel events**
   - Landing view, demo interaction, login click, auth success, first render,
     gallery view, and InterestGate capture.
   - Acceptance: PMF/funnel data can be inspected without raw production access.

### Cross-Lane Execution Order

1. Janua client registration/rotation.
2. Browser login/session acceptance.
3. Production secret and migration readiness.
4. Authenticated GPU + cancellation + multi-modal smokes.
5. BFF/session migration and browser E2E tests.
6. Observability/CI cleanup.
7. Landing/demo conversion instrumentation.

Janua remains the critical path blocker. All other lanes can begin in parallel,
but CEQ cannot be marked fully functional for users until Janua accepts the CEQ
client and a real browser session reaches the Studio shell.

## Remaining Roadmap To Full Stability

The items below are what remains after the current stabilization patch. They are ordered by production risk and should be treated as the next execution plan.

### P0 — Production Rollout Gates

1. **Provision runtime callback/webhook secrets**
   - Add `JOB_COMPLETION_CALLBACK_TOKEN` to production `ceq-secrets`.
   - The API requires this in production; workers use the same value when POSTing completion reports.
   - Add `JOB_WEBHOOK_SECRET` before enabling user-provided `webhook_url` delivery.
   - Acceptance can now be checked with admin `GET /v1/operations/status`.

2. **Run and verify migrations**
   - Apply Alembic head through the GitOps migration job.
   - Confirm existing `outputs` rows have non-null `filename`, `file_type`, and `file_size_bytes`.
   - Confirm `uq_outputs_job_storage_uri` exists after `20260514_outputs_job_storage_unique`.
   - Acceptance can now use `GET /v1/operations/status` for the visible Alembic revision, with DB-level constraint proof handled by the optional PostgreSQL migration test harness.

3. **Run a real end-to-end GPU smoke**
   - Studio/API job submission -> Redis pending queue -> worker execution -> R2 upload -> API callback -> PostgreSQL output row -> Studio gallery render.
   - Use `scripts/production-smoke.sh` with `CEQ_AUTH_TOKEN` and `CEQ_TEMPLATE_ID` after deployment.
   - Add `CEQ_RUN_OPERATIONS_STATUS=true` and `CEQ_ADMIN_AUTH_TOKEN` to verify admin readiness gates in the same run.
   - Acceptance: the final job is `completed`, output rows are durable, and gallery URLs open from the browser.

4. **Run active cancellation smoke**
   - Submit a long-running GPU job.
   - Cancel it from Studio/API while it is running.
   - Use `CEQ_RUN_CANCEL_SMOKE=true` with `CEQ_CANCEL_TEMPLATE_ID`.
   - Acceptance: worker interrupts ComfyUI, API remains `cancelled`, and no late success report overwrites the cancelled state.

5. **Run multi-modal artifact smoke**
   - Exercise image, video, audio, and 3D/model workflows.
   - Use `CEQ_TEMPLATE_SMOKES_JSON` to run modality template IDs in one smoke pass.
   - Acceptance: each output persists with correct MIME/metadata and renders or opens from Studio gallery.

6. **Verify network policy paths**
   - Worker -> `ceq-api` callback path.
   - Worker/API -> Redis DB 14.
   - Worker/API -> Cloudflare R2.

7. **Verify Janua production client**
   - Confirm Janua knows the active CEQ client ID and `https://app.ceq.lol/auth/callback`.
   - Live check on 2026-05-14 returned `invalid_client: Unknown client_id` for the documented client ID.
   - CEQ Studio now uses Janua OIDC `/api/v1/oauth/*` endpoints and reserves `ceq.lol` for landing/demo traffic.
   - CEQ Studio routes are server-gated by CEQ session cookies before the React shell renders.
   - Acceptance: production Studio login succeeds, `/api/auth/session` bootstraps the browser, and websocket auth token can be used for job streams.

### P1 — Functional Correctness

1. **Implement user-provided job webhooks** — completed locally
   - `webhook_url` completion delivery now sends signed terminal job events.
   - Delivery attempts, failures, and success metadata are recorded under `job.output_metadata.webhook_delivery`.
   - Production still needs `JOB_WEBHOOK_SECRET` provisioned before webhook delivery is enabled.

2. **Implement active worker cancellation** — completed locally
   - API records `cancel_requested=true`, publishes a per-job cancel command, and prevents late success reports from overriding `cancelled`.
   - Workers subscribe while processing a job, cancel the handler task, interrupt ComfyUI, and report durable `cancelled`.
   - Production acceptance still requires a real running GPU cancel smoke after rollout.

3. **Broaden worker output collection** — completed locally
   - ComfyUI descriptors now collect image, video, audio, model, and arbitrary file outputs.
   - Storage descriptors include expanded MIME mapping plus image dimensions, WAV duration, best-effort MP4/MOV duration, and GLB metadata.
   - Studio gallery now renders video controls, audio controls, and 3D/model categorization.
   - Production acceptance still requires video/audio/3D template smoke coverage.

### P2 — Reliability Hardening

1. **Add callback retry and dead-letter handling** — completed locally for worker callbacks
   - Failed worker -> API callbacks retry with configurable backoff.
   - Exhausted callbacks land in Redis `ceq:jobs:completion:dead` and mark `ceq:job:{job_id}` with callback failure metadata.
   - Admin operations endpoints now list, replay, and discard those dead letters.

2. **Add DB-level idempotency** — completed locally
   - Added Alembic revision `20260514_outputs_job_storage_unique`.
   - Migration removes duplicate `(job_id, storage_uri)` rows before adding `uq_outputs_job_storage_uri`.
   - Keep the app-level idempotency already added.

3. **Add production-grade migration tests** — completed locally
   - Added a deterministic migration operation test for dedupe SQL and constraint creation.
   - Added an optional PostgreSQL-backed regression harness gated by `CEQ_TEST_POSTGRES_URL`.

4. **Pin worker images by digest** — completed in GitOps
   - Deploy job now builds/signs `ceq-worker` on every deploy and requires `WORKER_DIGEST`.
   - Deploy commit `44f2e0b` pins `ceq-worker` by digest alongside API and Studio.
   - Next: reduce cold worker image build time with a cached base image or digest reuse for unchanged worker sources.

### P3 — Observability And Product Completion

1. **Add alerts and dashboards**
   - Queue depth, stuck running jobs, callback failures, R2 upload failures, GPU worker health, migration failures.
   - Prometheus counters now exist for key API runtime paths; dashboards and alert rules still need to be wired.

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
  - Next: production smoke for active cancellation and richer callback observability.

- **worker** (`apps/workers/src/ceq_worker`)
  - `handler.py`, `queue.py`, `storage.py`, `config.py`
  - Completed execution payloads, R2 descriptors, callback posting, and Redis fallback writes.
  - Next: production GPU smoke across image/video/audio/3D outputs and replay tooling for dead-lettered callbacks.

- **data**
  - `apps/api/src/ceq_api/alembic/versions/*`
  - Completed outputs schema alignment.
  - Next: PostgreSQL-backed migration test harness and live duplicate audit confirmation during rollout.

- **infra** (`infrastructure/k8s/*`)
  - `worker-deployment.yaml`, `secrets.yaml`
  - Completed callback token wiring and R2 env alias wiring.
  - Next: provision production tokens, verify NetworkPolicies, and monitor GitOps digest commits.

- **frontend** (`apps/studio/src`)
  - Completed gallery URL consumption through `public_url` fallback and added
    session-cookie auth gating for `app.ceq.lol`.
  - Next: browser E2E auth fixture after Janua client registration, then
    video/audio/3D smoke fixtures and output-type-specific gallery polish.

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
  - Built rich output descriptors, sent callbacks with auth, awaited async progress callbacks, added active cancellation, retried callbacks, and kept Redis fallback/dead-letter writes.

- **infrastructure/k8s**
  - `api-deployment.yaml`, `worker-deployment.yaml`, `secrets.yaml`
  - Wired callback env vars, token secret, API callback URL, and R2 bucket alias.

- **apps/studio**
  - `src/lib/api.ts`, gallery components, auth context/routes, middleware
  - Consumes `public_url` where available, preserves `storage_uri` fallback behavior, renders audio/video/model output types, and gates app-host Studio routes with CEQ session cookies.

- **docs/tests**
  - `docs/CEQ_STABILITY_ROADMAP.md`, `tests/*`, `scripts/production-smoke.sh`
  - Documents remediation and keeps tests/smokes in sync with runtime contracts.

## Completed Acceptance Criteria

- `/v1/jobs/{id}/cancel` reliably removes queued payload from Redis with the actual queued shape.
- `/v1/outputs` and `/v1/jobs/{id}/outputs` consistently use `Output` model fields.
- Worker completions persist final `Job` status and durable `Output` rows.
- `apps/api` migration chain has a committed revision that aligns `outputs` schema.
- Callback endpoint accepts worker completion payload and authenticates via shared token.
- Active worker cancellation interrupts running handler work and reports durable `cancelled`.
- Worker completion callback failures retry and dead-letter exhausted payloads.
- Output persistence has DB-level `(job_id, storage_uri)` idempotency.
- Worker/Studio output handling covers image, video, audio, model, and generic file descriptors.
- CI includes regression for at least:
  - synthesis template fallback logic
  - queue cancel payload
  - callback persistence idempotency
  - modern output response fields
