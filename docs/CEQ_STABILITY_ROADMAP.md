# CEQ Stability Roadmap and Remediation Plan

> **Last updated:** 2026-06-01
> **Status:** Identity wiring deployed; Studio token route accepts Janua client secret; browser proof captured, GPU production smokes remain open
> **Session wrap-up:** [`docs/CEQ_IDENTITY_AND_DEMO_WRAPUP.md`](./CEQ_IDENTITY_AND_DEMO_WRAPUP.md)  
> **Capped GA demo:** [`docs/GA_DEMO_DEFINITION.md`](./GA_DEMO_DEFINITION.md)  
> **Commercial GA:** [`docs/COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md)
> **Commercial launch pack:** [`docs/COMMERCIAL_LAUNCH_READINESS_PACK.md`](./COMMERCIAL_LAUNCH_READINESS_PACK.md)
> **Janua handoff:** [`docs/JANUA_AGENT_HANDOFF.md`](./JANUA_AGENT_HANDOFF.md)  
> **Platform agents:** [`docs/PLATFORM_AGENT_HANDOFFS.md`](./PLATFORM_AGENT_HANDOFFS.md)  
> **Canonical smoke runner:** `scripts/production-smoke.sh`  
> **Studio Docker smoke:** `scripts/studio-docker-smoke.sh`  
> **Production ops:** Enclii-first (web, API, CLI). Raw `kubectl`/SSH is break-glass only.

---

## Table of contents

1. [Purpose, mission, vision](#purpose-mission-vision)
2. [Current status snapshot](#current-status-snapshot-2026-06-01)
3. [Definition of done — full stability](#definition-of-done--full-stability)
4. [Commercial GA track](#commercial-ga-track)
5. [Critical path](#critical-path)
6. [Implementation phases](#implementation-phases)
7. [Execution schedule](#execution-schedule)
8. [Smoke matrix](#smoke-matrix-operator-quick-reference)
9. [Risk register](#risk-register-program-level)
10. [Immediate next actions](#immediate-next-actions-this-week)
11. [Stability declaration template](#stability-declaration-template)
12. [Product backlog (post-stability)](#product-backlog-post-stability)
13. [Historical closure record](#historical-closure-record)

---

## Purpose, mission, vision

### Purpose

ceq is MADFAM's internal generative-production service layer for turning prompts
and workflows into deterministic, persisted outputs across social, video, and 3D
modalities.

It combines:

- `ceq-studio` (Next.js) — execution UX, output gallery, queue monitor
- `ceq-api` (FastAPI) — auth, workflow orchestration, persistence, render pillar
- `ceq-workers` — GPU execution, ComfyUI, output upload pipeline
- Kubernetes + Enclii — shared infra (Redis DB 14, PostgreSQL, ingress, GitOps)

CEQ also ships the **asset pillar**: content-addressed `/v1/render/*` endpoints
and `@ceq/sdk` for stable URLs consumed across the MADFAM ecosystem.

### Mission

Make CEQ a **stable production execution primitive**: job dispatch and completion
must be reliably persisted, queryable, and replayable while keeping user
experience fast and predictable.

Operational translation: **submit → queue → worker → callback → DB → UI** must
be contractually deterministic, with explicit failure modes and operator
recovery paths.

### Vision

Run CEQ as a deterministic, observable, auditable system:

- Jobs are submitted once and tracked end-to-end
- Completion updates both Redis (real-time) and PostgreSQL (durable)
- Output metadata is consistent across DB, API responses, callbacks, and Studio UI
- Remediation is code-backed, test-covered, and smoke-verified before "done"
- Production health gates are enforced before declaring feature completion

Product positioning (from `docs/PRD.md`): a **high-velocity, hacker-centric
terminal** — ComfyUI power with streamlined UX, MADFAM ecosystem integration,
latent chaos → shipped content.

---

## Current status snapshot (2026-06-01)

### Verdict

**Infra-stable, user-incomplete.** Janua OAuth client is registered and the
deployed Studio token route accepts the Janua client secret. Browser login with
real credentials is now proven through `/api/auth/session` and `httpOnly`
session cookies. Runtime secrets (`operations/status`), template seeding, and GPU
production smokes still need operator proof before CEQ can be declared fully
healthy.

Commercial GA readiness remains ~47% (evidence-weighted) and is tracked as the
shared execution baseline in [`COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md).
Use the GA-critical board below for close-form status and the evidence audit for proof artifacts.

### Live production evidence

| Check | Result | Notes |
|-------|--------|-------|
| `https://ceq.lol` | HTTP 200 | Marketing/landing host |
| `https://api.ceq.lol/health` | `{"status":"ok","service":"ceq-api","version":"0.1.0"}` | API reachable |
| `https://api.ceq.lol/ready` | `status: ready`, `database: ok`, `redis: ok` | API dependencies reachable |
| `https://app.ceq.lol/` (no session) | HTTP 307 → login | Server-side auth gate |
| `https://app.ceq.lol/login` | HTTP 200 | Studio login surface |
| `https://api.ceq.lol/docs` | HTTP 404 | OpenAPI not exposed in prod |
| `https://api.ceq.lol/v1/jobs` | HTTP 307 → `/v1/jobs/` | trailing-slash contract is working |
| `POST /v1/render/card` (no auth) | 401 | Render pillar auth-gated |
| Janua OAuth for documented client | 302 → login (registered 2026-05-23) |
| `GET /v1/templates/` | 200 JSON | `{"templates": [], "total": 0, "skip": 0, "limit": 50}` |
| `GET /v1/credits/balance` (no auth) | 404 | Route not currently routable in public prod check |
| `GET /v1/operations/status` (no auth) | 401 | Expected for admin-only endpoint |
| `POST app.ceq.lol/api/auth/token` with bogus code | Janua `invalid_grant` | Client secret accepted |
| `GET /api/auth/session` (admin credentials) | 200 JSON | `user`, `roles`, and `access_token` returned; `ceq_access_token` / `ceq_refresh_token` cookies present |

### What is working

- Service topology and GitOps deploy path (ArgoCD `ceq-services`, digest-pinned
  images for API, Studio, Worker)
- Core APIs reachable; `/v1/render/*` pipeline implemented (card, thumbnail,
  audio, 3D) with R2 content-addressed cache
- DB, Redis, R2, CI scaffolding in place
- Job completion callback contract, retries, dead-letter replay, active
  cancellation — implemented and locally tested
- Studio host split (`ceq.lol` vs `app.ceq.lol`), session cookies,
  `/api/proxy` BFF, public auth-gate smoke passing
- Prometheus metrics, ServiceMonitor, alert rules, Grafana dashboard ConfigMap
  in `infrastructure/k8s/observability.yaml`
- OpenAPI disabled in production (`docs_url=None` when `ENVIRONMENT=production`)

### Local test matrix (last verified 2026-05-17)

| Suite | Result |
|-------|--------|
| `apps/api` | 305 passed, 2 skipped |
| `apps/workers` | 119 passed |
| `apps/studio` | 85 passed; typecheck passed |
| Alembic head | `20260514_outputs_job_storage_unique` (single head) |
| Public production smoke | `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh` green |

### Pinned production digests (kustomization.yaml)

| Service | Digest |
|---------|--------|
| ceq-api | `sha256:b3f832eb917123ebd05208d6c5a8a11a75804f7caa0f44c340bb362ed47259a4` |
| ceq-studio | `sha256:c8c87bc3fb6cf0c73c6e393d3b71841dec8fbe7a88e4ea7c43885939b4082360` |
| ceq-worker | `sha256:c8adcf5963578c5b82fa6962276ff6ff06cfde99b36f4981ec4dcaf9dfb069a8` |

Studio digest `sha256:1a03d7ef…` was rolled back after crash
(`Cannot find module '/app/server.js'`). See
[2026-05-18 digest guardrail](#2026-05-18-studio-digest-guardrail) in the
historical record.

### What blocks full stability

1. ~~Janua OAuth client unregistered~~ and ~~Studio token secret missing~~ → Template seeding and GPU production smokes
2. Production runtime secrets not verified live (`JOB_COMPLETION_CALLBACK_TOKEN`,
   `JOB_WEBHOOK_SECRET`)
3. Authenticated GPU E2E, cancellation, and multi-modal smoke not proven in prod
4. Alert routing and on-call runbooks not confirmed in Enclii observability tenant

Commercial GA has additional blockers beyond full stability: Dhanam-backed
billing or an approved pilot bridge, server-side credit/entitlement enforcement,
quota/rate/spend controls, support readiness, customer-facing legal/commercial
docs, and launch signoff. Track those in
[`COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md) and
[`COMMERCIAL_LAUNCH_READINESS_PACK.md`](./COMMERCIAL_LAUNCH_READINESS_PACK.md).

### GA-Critical evidence board (roadmap truth)

Use this as the roadmap-level priority closure board, synchronized with
[`COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md)
and `docs/DOCS_EVIDENCE_AUDIT_2026-06-01.md`.

| Priority | Category | Action | Status | Evidence status |
|----------|----------|--------|--------|----------------|
| P0-1 | Identity | Browser login on `app.ceq.lol` with operator credentials proves Studio shell session bootstrap. | Complete | `/api/auth/session` user payload and `httpOnly` session cookies captured |
| P0-2 | Runtime | `GET /v1/operations/status` passes with admin JWT (`callback`, `webhook`, `revision`, `dead-letter`) . | In progress | PR #38 updates Janua introspection fallback endpoints. Awaiting prod verification after merge to `main`. |
| P0-3 | Runtime | Authenticated GPU smoke and gallery durability (`job → callback → output`) | Not started | Not yet captured |
| P0-4 | Platform | Template catalog seeded (`/v1/templates/` returns non-empty IDs) | Inconsistent | Public evidence currently empty |
| P0-5 | Stability | Cancel + multi-modal + strict smoke pass in production | Not started | Not yet captured |
| P1-1 | Monetization | Dhanam-backed plan/checkout and funded entitlements live | Not started | Not yet captured |
| P1-2 | Monetization | Entitlements are enforced server-side (not UI-only) | In progress | Role/entitlement-claim guards landed |
| P1-3 | Reliability | Alerts and rollback drills hit on-call/owner paths | Not started | Not yet proven |
| P1-4 | Legal/commercial | Terms, privacy, pricing, and support docs are linked in user flows | In progress | Public landing and `/billing` link legal/commercial routes; legal approval still pending |
| P1-5 | Launch | Paid pilot + launch signoff with incident/runbook rehearsals | Not started | Not yet executed |

### Roadmap closure priority board

Status is tracked here for execution planning; completion is evidence-linked in
the commercial GA plan and evidence audit.

| Priority | Action | Status | Completion rule |
|----------|--------|--------|-----------------|
| P0-1 | Browser login on `app.ceq.lol` with operator credentials and stable session proof. | Complete | Login succeeds + `/api/auth/session` returns user identity |
| P0-2 | `GET /v1/operations/status` with admin JWT returns callback/webhook readiness and migration revision. | In progress | PR #38 updates API Janua introspection path. Awaiting prod verification. |
| P0-3 | Authenticated production GPU smoke and gallery durability check. | Not started | End-to-end output URL + callback row + PostgreSQL output row |
| P0-4 | Seed templates + persistent template IDs in production. | Inconsistent | `GET /v1/templates/` returns non-empty templates for smoke |
| P1-1 | Strict smoke pass (`CEQ_STRICT_SMOKE=true`), dead-letter thresholds, and rollback/alarm drill proof. | Not started | Smoke script passes with documented alert + on-call path references |

### 2026-05-22 implementation progress

Engineering work landed in-repo (operator-only P0 items remain open):

| Phase | Item | Status |
|-------|------|--------|
| **Baseline** | Public production smoke | ✅ Green (`CEQ_PUBLIC_ONLY=true`) |
| **Phase 4** | Studio Docker entrypoint fix | ✅ `CMD node apps/studio/server.js`; static at `apps/studio/.next/static` |
| **Phase 4** | `scripts/studio-docker-smoke.sh` | ✅ Added |
| **Phase 4** | CI `Studio · Docker smoke` job | ✅ `.github/workflows/ci.yaml` |
| **Phase 4** | Deploy waits for CI + Studio smoke before push | ✅ `.github/workflows/deploy.yaml` |
| **Phase 5** | WebSocket auth via session bootstrap | ✅ `resolveStreamAuthToken()` + async `subscribeToJob()` |
| **Phase 6** | `ECOSYSTEM.md` drift fix | ✅ Ports, render status, Janua auth note |
| **Phase 0** | Janua OAuth client registration | ✅ Janua registered 2026-05-23; CEQ secret mount in `studio-deployment.yaml` |
| **Phase 0** | Studio token secret + browser proof | ✅ Token route proof green; browser proof captured via `/api/auth/session` |
| **Phase 1** | Production callback/webhook secrets | ⏳ Operator — verify via `operations/status` |
| **Phase 2** | Authenticated GPU smokes | ⏳ Blocked on Phase 1 |
| **Phase 4** | Studio Docker regression CI gate | ✅ Closed 2026-05-22 |
| **Phase 4** | GitHub branch protection on `main` | ✅ Enabled 2026-06-01; requires six CEQ CI checks + one review |
| **Phase 4** | Playwright auth E2E in CI | ✅ 6/6 green locally (`mock-janua-server` + `next dev`; middleware allows `127.0.0.1`) |

### 2026-05-23 session close

| Item | Status |
|------|--------|
| Janua OAuth P0 | ✅ Registered; authorize 302 |
| K8s `JANUA_CLIENT_SECRET` mount | ✅ Manifest on `main` |
| CI (API/workers ruff + Studio gates) | ✅ Green |
| Studio token secret accepted | ✅ Live token route proof (`invalid_grant` for bogus code, 2026-06-01) |
| Browser login acceptance | ✅ `/api/auth/session` verified with user identity and `httpOnly` cookies |
| Session wrap-up doc | ✅ [`CEQ_IDENTITY_AND_DEMO_WRAPUP.md`](./CEQ_IDENTITY_AND_DEMO_WRAPUP.md) |

## Definition of done — full stability

CEQ is **fully healthy** when all gates below pass without manual exceptions:

| Gate | Proof |
|------|-------|
| **Public edge** | `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh` green |
| **Identity** | Real browser login on `app.ceq.lol` → session cookies → Studio shell |
| **Runtime secrets** | `GET /v1/operations/status` reports callback + webhook readiness green |
| **Schema** | Alembic head `20260514_outputs_job_storage_unique` applied; `uq_outputs_job_storage_uri` live |
| **GPU E2E** | Authenticated smoke: submit → Redis → worker → R2 → callback → PostgreSQL → gallery |
| **Cancellation** | Active cancel smoke on running GPU job; late success cannot overwrite `cancelled` |
| **Multi-modal** | Image + video + audio + 3D template smokes pass in prod |
| **Observability** | Alerts route to on-call; runbooks linked; dashboard usable |
| **CI/CD** | PRs cannot merge without CI; deploy cannot promote broken Studio/Worker images |
| **Docs truth** | `ECOSYSTEM.md`, README, and this roadmap match live behavior |

**Rule:** No "full stability" declaration until P0 phases complete. P1/P2 work
may run in parallel where noted, but must not delay P0 closure.

---

## Commercial GA Track

Full stability is the operational prerequisite for CEQ, but it is not
commercial GA. Commercial GA means CEQ can be sold, onboarded, metered,
supported, and operated for paying users without manual exceptions.

Current planning estimate:

| Milestone | Readiness | Notes |
|-----------|-----------|-------|
| Public technical demo | Ready now | Public edge and API evidence are green |
| Capped GA demo | ~55-65% | Browser login, template seeding, and one GPU golden path remain open |
| Full stability | ~50-60% | Strict smoke, alert routing, and governance remain open |
| Limited commercial pilot | ~50-60% | Credit/entitlement/queue/metering primitives landed; needs funded balances, GPU proof, support workflow |
| Commercial GA | ~47% | Needs Dhanam billing, prod GPU proof, and alert/support/legal launch pack |

Commercial GA gates:

| Gate | Required proof |
|------|----------------|
| Commercial scope/SKU | Launch templates, pricing, limits, and non-goals frozen |
| Identity/accounts | Login, session refresh, logout, account/tenant boundaries verified |
| Runtime fulfillment | Strict GPU smoke passes and output persistence is durable |
| Billing | Dhanam checkout/invoice path or approved pilot billing bridge works |
| Credits | Initial ledger/API, Studio account balance, and feature-flagged render/GPU debit-refund plumbing landed; billing reconciliation still required |
| Entitlements | Initial premium/pro API guard landed; Dhanam-backed plan source still required |
| Quotas/abuse | Role/entitlement-aware active-job caps landed; Dhanam-backed queue/rate/spend limits still required |
| Observability/support | Alerts route to on-call; support macros and escalation runbooks exist |
| Security/legal | AuthZ, audit logs, terms, privacy, acceptable-use, and retention docs are ready |
| Launch signoff | Product, engineering, platform, and support sign off with evidence links |

Primary remediation plan:
[`docs/COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md) plus the
[`docs/COMMERCIAL_LAUNCH_READINESS_PACK.md`](./COMMERCIAL_LAUNCH_READINESS_PACK.md).

Target windows after browser login proof:

- Capped GA demo: 3-7 days
- Limited commercial pilot: 2-4 weeks
- Commercial GA: 6-10 weeks

---

## Critical path

```
Janua OAuth client registration
        ↓
Browser login proof (app.ceq.lol)
        ↓
Provision callback/webhook secrets → operations/status green
        ↓
Authenticated GPU smoke
        ↓
Cancel + multi-modal smokes
        ↓
Alert routing + runbooks + CI guardrails
        ↓
Declare full stability
        ↓
Server-side credits + entitlements + quotas
        ↓
Billing/support/legal launch pack
        ↓
Limited commercial pilot
        ↓
Commercial GA declaration
```

Runtime secrets plus authenticated GPU smokes remain the **critical path blocker**.
Other lanes can run in parallel, but CEQ cannot be marked fully functional for
users until `operations/status` is green and authenticated production GPU smokes
pass.

---

## Implementation phases

### Phase 0 — Unblock identity (P0)

**Owner:** Janua operator + `apps/studio`  
**Duration:** ~1–2 days  
**Operator runbook:** [`docs/JANUA_OPERATOR.md`](./JANUA_OPERATOR.md)  
**Janua agent handoff:** [`docs/JANUA_AGENT_HANDOFF.md`](./JANUA_AGENT_HANDOFF.md)  
**Enclii-first:** Register client via Janua admin or Enclii secrets adapter.
Record adapter gap if raw Janua admin is used.

#### Tasks

1. **Register or rotate Janua OAuth client**
   - Name: `CEQ Studio`
   - Client ID (documented): `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk` — rotate if
     Janua no longer recognizes it
   - Redirect URIs:
     - `https://app.ceq.lol/auth/callback` (production)
     - `http://localhost:5801/auth/callback` (development)
   - Grant types: `authorization_code`, `refresh_token`
   - Scopes: `openid`, `profile`, `email`
   - Janua OIDC endpoints:
     - Authorization: `https://auth.madfam.io/api/v1/oauth/authorize`
     - Token: `https://auth.madfam.io/api/v1/oauth/token`
     - UserInfo: `https://auth.madfam.io/api/v1/oauth/userinfo`

2. **Update secrets if client ID rotates**
   - `NEXT_PUBLIC_JANUA_CLIENT_ID` (Studio build-time)
   - `JANUA_CLIENT_SECRET` (K8s `ceq-janua-client-secret` / `external-secret.yaml`)
   - Redeploy Studio via GitOps if client ID changes

3. **Browser acceptance checklist**
   - [x] No-cookie `https://app.ceq.lol/` → `/login?returnTo=%2F`
   - [x] Janua login succeeds (no `invalid_client`)
   - [x] `/auth/callback` sets httpOnly CEQ session cookies
   - [x] `GET /api/auth/session` bootstraps Studio browser state
   - [ ] Token refresh rotates cookies correctly
   - [ ] Logout clears CEQ cookies before Janua logout redirect
   - [ ] Studio API calls succeed via `/api/proxy`
   - [ ] Job WebSocket stream works with token from session bootstrap

#### Acceptance

```bash
CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh
# Plus manual browser login with real credentials on app.ceq.lol
```

#### Risks

| Risk | Mitigation |
|------|------------|
| Wrong redirect URI | Match exactly — trailing slash matters |
| Stale Studio image | Confirm ArgoCD rolled digest after env change |
| WebSocket still uses legacy token path | Track in Phase 5; REST already proxied |

---

### Phase 1 — Production runtime secrets and schema (P0)

**Owner:** Platform operators + `apps/api` + `apps/workers`  
**Duration:** ~1 day  
**Prerequisite:** None (parallel with Phase 0 tail)  
**Enclii-first:** Provision via Enclii secrets; use break-glass
`secrets.local.yaml` only if adapter missing — record gap in runbook.

#### Tasks

1. **Provision secrets in production `ceq-secrets`**
   - `JOB_COMPLETION_CALLBACK_TOKEN` — shared API/worker token (32+ byte random)
   - `JOB_WEBHOOK_SECRET` — HMAC for user-provided job completion webhooks
   - Confirm `infrastructure/k8s/external-secret.yaml` syncs from vault, or apply
     operator-local manifest once

2. **Verify via admin API (no raw pod access)**

   ```bash
   CEQ_RUN_OPERATIONS_STATUS=true \
   CEQ_REQUIRE_OPERATIONS_STATUS=true \
   CEQ_REQUIRE_WEBHOOK_SECRET=true \
   CEQ_ADMIN_AUTH_TOKEN=<admin-jwt> \
   scripts/production-smoke.sh
   ```

3. **Confirm migration applied**
   - ArgoCD PreSync job (`db-migrate-job.yaml`) ran `alembic upgrade head`
   - Expected revision: `20260514_outputs_job_storage_unique`

   ```bash
   CEQ_EXPECT_ALEMBIC_REVISION=20260514_outputs_job_storage_unique \
   CEQ_RUN_OPERATIONS_STATUS=true \
   CEQ_ADMIN_AUTH_TOKEN=<admin-jwt> \
   scripts/production-smoke.sh
   ```

4. **Establish dead-letter baseline**

   ```bash
   CEQ_EXPECT_MAX_COMPLETION_DEAD_LETTERS=0 \
   CEQ_RUN_OPERATIONS_STATUS=true \
   CEQ_ADMIN_AUTH_TOKEN=<admin-jwt> \
   scripts/production-smoke.sh
   ```

5. **Verify worker env alignment**
   - Worker deployment reads same `JOB_COMPLETION_CALLBACK_TOKEN` as API
   - Worker posts to `POST /v1/jobs/{job_id}/outputs/report`

#### Acceptance

- `GET /v1/operations/status` → callback ready, webhook ready, alembic revision
  correct, dead-letter depth ≤ threshold
- Worker and API share callback token value

---

### Phase 2 — Production GPU runtime proof (P0)

**Owner:** Operators + `apps/api` + `apps/workers` + GPU provider (Vast.ai)  
**Duration:** ~2–4 days  
**Prerequisites:** Phase 0 (auth token for smokes) + Phase 1 (secrets verified)

#### Tasks

1. **Ensure worker pods are running and reachable**
   - Worker digest pinned in `infrastructure/k8s/kustomization.yaml`
   - Vast.ai instances healthy OR in-cluster worker deployment scaled > 0
   - NetworkPolicies allow:
     - Worker → API callback
     - Worker/API → Redis DB 14
     - Worker/API → Cloudflare R2 (`ceq-assets`)

2. **Seed templates if DB is empty**
   - Operator one-shot: `infrastructure/k8s/seed-templates-job.yaml` (excluded
     from kustomize bundle by design)
   - Record template UUIDs in operator runbook for smoke env vars
   - Repo ships 6 ComfyUI workflow JSON files under `templates/`:
     - `social/flux-schnell.json`, `social/instantid-portrait.json`
     - `video/hunyuan-video.json`
     - `3d/triposr-image-to-3d.json`
     - `utility/sdxl-txt2img.json`, `utility/image-upscaler.json`

3. **Run authenticated end-to-end GPU smoke**

   ```bash
   CEQ_AUTH_TOKEN=<janua-jwt> \
   CEQ_TEMPLATE_ID=<image-template-uuid> \
   CEQ_RUN_OPERATIONS_STATUS=true \
   CEQ_ADMIN_AUTH_TOKEN=<admin-jwt> \
   CEQ_EXPECT_OUTPUTS=true \
   scripts/production-smoke.sh
   ```

   Validates: job reaches `completed`, outputs durable, gallery URLs open.

4. **Run active cancellation smoke**

   ```bash
   CEQ_AUTH_TOKEN=<jwt> \
   CEQ_RUN_CANCEL_SMOKE=true \
   CEQ_REQUIRE_CANCEL_SMOKE=true \
   CEQ_CANCEL_TEMPLATE_ID=<long-running-template-uuid> \
   CEQ_CANCEL_AFTER_SECONDS=10 \
   scripts/production-smoke.sh
   ```

5. **Run multi-modal artifact smoke**

   ```bash
   CEQ_AUTH_TOKEN=<jwt> \
   CEQ_TEMPLATE_SMOKES_JSON='[
     {"label":"image","template_id":"<uuid>","params":{}},
     {"label":"video","template_id":"<uuid>","params":{}},
     {"label":"audio","template_id":"<uuid>","params":{}},
     {"label":"3d","template_id":"<uuid>","params":{}}
   ]' \
   scripts/production-smoke.sh
   ```

6. **Render pillar smoke (auth-gated)**

   ```bash
   curl -H "Authorization: Bearer $CEQ_AUTH_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"template":"card-standard","data":{"title":"Smoke","accent":"#FF5A3C"}}' \
     https://api.ceq.lol/v1/render/card
   ```

   Confirm R2 cache hit on second identical call (`cached: true`).

7. **Verify network policy paths under load**
   - Worker → `ceq-api` callback path
   - Worker/API → Redis DB 14
   - Worker/API → Cloudflare R2 egress

#### Acceptance

All three smoke modes pass with strict gate:

```bash
CEQ_STRICT_SMOKE=true \
CEQ_AUTH_TOKEN=<jwt> \
CEQ_ADMIN_AUTH_TOKEN=<admin-jwt> \
CEQ_TEMPLATE_ID=<image-template-uuid> \
CEQ_CANCEL_TEMPLATE_ID=<long-running-uuid> \
CEQ_TEMPLATE_SMOKES_JSON='[...]' \
scripts/production-smoke.sh
```

(`CEQ_STRICT_SMOKE=true` enables operations + cancel requirements automatically.)

#### Risks

| Risk | Mitigation |
|------|------------|
| GPU worker cold start / model download | Increase `CEQ_POLL_TIMEOUT_SECONDS` (default 600) |
| Vast.ai spend/runaway | Worker orchestrator spending limits |
| Template UUID mismatch | Document UUIDs after seed job |
| Missing GPU models on worker | Prefetch via worker model cache; verify R2 model paths |

---

### Phase 3 — Operational closure (P1)

**Owner:** Platform observability + on-call  
**Duration:** ~2–3 days (parallel with Phase 2 tail)  
**Enclii-first:** Configure alert receivers in Enclii observability tenant.

#### Tasks

1. **Confirm alert routing**
   - Assets: `infrastructure/k8s/observability.yaml`
   - Wire receivers for:
     - Queue depth high
     - Stale running jobs
     - Completion dead-letter growth
     - Webhook delivery failures
     - Alembic revision drift

2. **Write operator runbooks** (in `docs/` or `internal-devops/`)
   - Dead-letter replay:
     `POST /v1/operations/completion-dead-letters/{index}/replay`
   - Force re-migration: delete `ceq-db-migrate` job → ArgoCD recreates PreSync
   - Worker/API digest rollback: revert kustomization digest commit
   - Janua client rotation procedure
   - Incident: empty Service endpoints (kustomize selector mismatch class)

3. **Dashboard review**
   - Validate Grafana panels: queue depth, callback rates, cancellation counts
   - Assign dashboard owner

#### Acceptance

- Test alert fires to intended channel (synthetic queue depth or dead-letter
  injection in staging)
- Runbook links attached to alert annotations in Enclii tenant

---

### Phase 4 — CI/CD hardening (P1)

**Owner:** Repo maintainers + GitHub org admins  
**Duration:** ~2–3 days (parallel with Phase 2–3)

#### Tasks

1. **Enable branch protection on `main`**
   - Require status checks:
     - `NetworkPolicy port consistency`
     - `API · lint + tests`
     - `Workers · lint + tests`
     - `Studio · lint + typecheck + vitest`
     - `Studio · Docker smoke`
     - `Studio · Playwright auth`
   - Require PR before merge
   - Update `AGENTS.md` and README when enforced
   - Org admin command (requires `gh` admin on repo):

     ```bash
     gh api repos/madfam-org/ceq/branches/main/protection -X PUT \
       -f required_status_checks[strict]=true \
       -f required_status_checks[contexts][]='NetworkPolicy port consistency' \
       -f required_status_checks[contexts][]='API · lint + tests' \
       -f required_status_checks[contexts][]='Workers · lint + tests' \
       -f required_status_checks[contexts][]='Studio · lint + typecheck + vitest' \
       -f required_status_checks[contexts][]='Studio · Docker smoke' \
       -f required_status_checks[contexts][]='Studio · Playwright auth' \
       -f enforce_admins=true \
       -f required_pull_request_reviews[dismiss_stale_reviews]=true \
       -f required_pull_request_reviews[required_approving_review_count]=1 \
       -f restrictions=
     ```

2. **Fix Studio Docker regression gate (2026-05-18 incident)**
   - Bad digest crashed: `Cannot find module '/app/server.js'`
   - Add CI/deploy step: build Studio Docker image + container smoke
     (`node /app/server.js` or HTTP health inside container)
   - Prevent bad Studio digests from reaching kustomization commit

3. **Worker build cache / deploy velocity**
   - Cold worker build ~26 min blocks deploy velocity
   - Add cached base image layer or skip worker rebuild when `apps/workers/**`
     unchanged (content-hash gate in `.github/workflows/deploy.yaml`)

4. **Optional: gate deploy on CI**
   - Deploy workflow waits for CI success on same SHA before digest commit
   - Or: deploy only from tagged releases

5. **Add Playwright auth E2E to CI**
   - Mock Janua OIDC responses deterministically
   - Cover: unauthenticated redirect, callback cookie set, session bootstrap,
     logout
   - Separate manual live-auth smoke doc for production

#### Acceptance

- Bad Studio image caught in CI before GitOps commit
- PR to `main` cannot merge with failing tests
- Playwright auth suite green in CI

#### Already closed in this lane

- [x] Node 24 in CI (was Node 20)
- [x] Next `outputFileTracingRoot` warning fixed (`experimental` in
  `apps/studio/next.config.mjs`)
- [x] Worker digest required on every deploy
- [x] Studio Docker smoke script + CI job (2026-05-22)
- [x] Deploy workflow waits for CEQ CI success on same SHA (2026-05-22)
- [x] Studio container smoke before GHCR push (2026-05-22)
- [x] Fixed standalone entrypoint path (`apps/studio/server.js`) (2026-05-22)

---

### Phase 5 — Auth and session completion (P1)

**Owner:** `apps/studio`  
**Duration:** ~3–5 days  
**Prerequisite:** Phase 0 browser login proof

#### Tasks

1. **WebSocket session migration**
   - Move job stream auth off legacy browser `localStorage` bearer token
   - Use session bootstrap token or same-origin WS proxy

2. **Remove legacy direct-token path**
   - After WS migration + prod proof, delete browser bearer fallback
   - Update `@ceq/sdk` docs for service-account / machine token consumers

3. **Browser E2E in production smoke doc**
   - Scripted checklist or Playwright against staging with real Janua

#### Acceptance

- No readable bearer tokens in browser storage for REST or WebSocket
- Reload + deep-link navigation works without re-login within refresh window

#### Already closed in this lane

- [x] REST API calls proxied through `/api/proxy` with session cookies
- [x] `GET /api/auth/session` bootstrap + refresh
- [x] Server-gated Studio routes on `app.ceq.lol`
- [x] Host split: `ceq.lol` landing vs `app.ceq.lol` authenticated app
- [x] WebSocket token resolves from session bootstrap when in-memory token empty (2026-05-22)

---

### Phase 6 — Documentation and hygiene (P2)

**Owner:** Repo maintainers  
**Duration:** ~1–2 days (anytime after Phase 0)

#### Tasks

1. **Fix `ECOSYSTEM.md` drift**
   - Remove stale "audio/3D rendering stubs return 501" claim (implemented in
     `/v1/render/audio` and `/v1/render/3d`)
   - Correct container ports: Studio 5801, API 5800 (not 3000/8000)
   - Note render endpoints require Janua auth in production

2. **Secret hygiene**
   - Migrate fully to ExternalSecret; remove `REPLACE_ME` from applied manifests
   - Rotate any credentials in operator-local examples
   - Record Enclii adapter gap if ExternalSecret sync is still manual

3. **Reconcile README and PRODUCTION_DEPLOYMENT.md**
   - Align deployment status dates and action-required items with this roadmap

4. **Update this roadmap on each phase closure**
   - Mark phases complete with smoke command outputs + dates

#### Acceptance

- `ECOSYSTEM.md`, README, `PRODUCTION_DEPLOYMENT.md`, and this file agree on
  live behavior

---

### Phase 7 — Product backlog (post-stability, P2/P3)

These do **not** block the stability declaration. Track separately after P0–P1
gates pass.

| Item | Owner | Notes |
|------|-------|-------|
| Template catalog expansion | Product + eng | 6 checked-in workflow JSON files + 13 seeded DB templates; PRD lists dozens — prioritize social + video MVP |
| Publishing channels | `apps/api` outputs | Twitter/Instagram/LinkedIn/Discord `coming_soon`; webhook only live |
| Monetization | Product + Dhanam + API + Studio | InterestGate exists; initial API-side premium guard, credit ledger, role/entitlement-aware active-job caps, Studio account balance, and feature-flagged render/GPU debits landed 2026-06-01; commercial GA still requires Dhanam checkout, billing reconciliation, Dhanam-backed quotas, and full Studio billing UX per [`COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md) |
| Landing conversion | Studio landing | Outcome-first landing with product proof panel, simulated deterministic render/cache-hit demo, founding-pilot CTAs, and lightweight event hooks; connect analytics sink after deploy |
| Furnace migration | Workers | Vast.ai today; Furnace provider not deployed |
| PRD promotion | Product | Move from Draft v0.1.0 to accepted MVP spec |
| Intelligence layer | API | `synthesis`, `intent`, `printability` — define prod acceptance separately |
| Redis Sentinel | Platform | Shared infra maturity gap per AGENTS.md dependency table |
| Worker CI/CD optimization | Eng | Reduce ~26 min cold worker build |

---

## Execution schedule

| Week | Focus | Exit criteria |
|------|-------|---------------|
| W1 D1–2 | Phase 0: Janua client | Browser login works |
| W1 D3 | Phase 1: Secrets + migration verify | `operations/status` green |
| W1 D4–5 | Phase 2: GPU E2E + cancel | Authenticated smokes pass |
| W2 D1 | Phase 2: Multi-modal + render | `CEQ_STRICT_SMOKE=true` green |
| W2 D2–3 | Phase 3: Alerts + runbooks | On-call wired |
| W2 D3–5 | Phase 4: CI hardening | Branch protection + Studio Docker gate |
| W3 | Phase 5–6: Session cleanup + docs | Declare full stability |
| W4-6 | Commercial pilot foundation | Credits, entitlements, quotas, support workflow |
| W6-10 | Commercial GA hardening | Billing reconciliation, abuse controls, launch signoff |

Parallel lanes: Phase 3 + 4 start during Phase 2 tail; Phase 6 anytime after
Phase 0. Commercial GA phases start only after capped demo proof unless a task is
strictly additive and does not weaken the P0 stability gates.

---

## Smoke matrix (operator quick reference)

| Scenario | Command flags |
|----------|---------------|
| Public edge only | `CEQ_PUBLIC_ONLY=true` |
| Public endpoint matrix | `scripts/capture-public-endpoint-matrix.sh` |
| Full strict gate | `CEQ_STRICT_SMOKE=true CEQ_AUTH_TOKEN=… CEQ_TEMPLATE_ID=…` |
| Operations readiness | `CEQ_RUN_OPERATIONS_STATUS=true CEQ_REQUIRE_OPERATIONS_STATUS=true CEQ_ADMIN_AUTH_TOKEN=…` |
| Webhook secret required | `CEQ_REQUIRE_WEBHOOK_SECRET=true` |
| Cancel proof | `CEQ_RUN_CANCEL_SMOKE=true CEQ_REQUIRE_CANCEL_SMOKE=true CEQ_CANCEL_TEMPLATE_ID=…` |
| Multi-modal | `CEQ_TEMPLATE_SMOKES_JSON='[…]'` |
| Dead-letter guard | `CEQ_EXPECT_MAX_COMPLETION_DEAD_LETTERS=0` |
| Alembic revision check | `CEQ_EXPECT_ALEMBIC_REVISION=20260514_outputs_job_storage_unique` |
| App auth gate (default on) | `CEQ_EXPECT_APP_AUTH_REDIRECT=true` |

### Single "declare stability" command

Run after Phases 0–2 prerequisites are met:

```bash
CEQ_STRICT_SMOKE=true \
CEQ_AUTH_TOKEN=<jwt> \
CEQ_ADMIN_AUTH_TOKEN=<admin-jwt> \
CEQ_TEMPLATE_ID=<image-template-uuid> \
CEQ_CANCEL_TEMPLATE_ID=<long-running-uuid> \
CEQ_TEMPLATE_SMOKES_JSON='[...]' \
CEQ_EXPECT_MAX_COMPLETION_DEAD_LETTERS=0 \
CEQ_EXPECT_ALEMBIC_REVISION=20260514_outputs_job_storage_unique \
scripts/production-smoke.sh
```

### Public-only gate (no credentials)

```bash
CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh
```

Verifies: API health, `ceq.lol` HTTP 200, host-split redirects, unauthenticated
app gate on `app.ceq.lol`.

---

## Risk register (program level)

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Janua client blocked on operator availability | High | Blocks all user value | Escalate P0; temporary service-account JWT for SDK smokes only |
| GPU provider outage during acceptance | Medium | Delays declaration | Run smokes during known-good Vast window; document retry |
| Secret mismatch API vs worker | Medium | Silent callback failures | `operations/status` gate before GPU smoke |
| Studio Docker regression recurs | Medium | 502 on app host | CI container smoke before digest commit |
| kustomize selector mismatch (2026-05-04 class) | Low | Hours-long 502 | Never use `commonLabels` with conflicting pod template labels; use `labels:` with `includeSelectors: false` |
| Scope creep into product features | High | Stability never declared | Freeze Phase 7 until P0–P1 gates pass |

---

## Immediate next actions (this week)

1. [x] **DONE** **CEQ operator:** Complete real browser login proof for `app.ceq.lol` — *critical path*
2. [ ] **BLOCKED** **Platform operator:** Provision `JOB_COMPLETION_CALLBACK_TOKEN` +
   `JOB_WEBHOOK_SECRET` via Enclii/ExternalSecret
3. [ ] **BLOCKED** **CEQ operator:** Run `operations/status` smoke with admin JWT
4. [ ] **BLOCKED** **CEQ operator:** Seed templates if needed; capture UUIDs in runbook
5. [ ] **BLOCKED** **CEQ operator:** Run authenticated GPU + cancel + multi-modal smokes
6. [ ] **IN PROGRESS** **Product + engineering:** Freeze commercial launch SKU, credit units, and
   supported template catalog
7. [ ] **IN PROGRESS** **API + Dhanam:** Replace initial role/entitlement checks and
   role/entitlement-claim quotas with Dhanam plan state; fund balances and enable
   render/GPU debit flags for a pilot cohort

---

## Stability declaration template

When all P0/P1 gates pass, add this section to the top of this document:

```markdown
## Full Stability Declared — YYYY-MM-DD

- Janua client: registered, browser login verified
- Secrets: callback + webhook provisioned, operations/status green
- GPU E2E: strict smoke passed (attach log reference)
- Cancel + multi-modal: passed
- Alerts: routed to <channel>, runbooks at <path>
- CI: branch protection enforced; Studio Docker gate active
- Docs: ECOSYSTEM.md reconciled

Remaining product debt tracked in Phase 7 backlog.
Commercial launch work tracked in
[`COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md) and
[`COMMERCIAL_LAUNCH_READINESS_PACK.md`](./COMMERCIAL_LAUNCH_READINESS_PACK.md).
```

---

## Product backlog (post-stability)

See [Phase 7](#phase-7--product-backlog-post-stability-p2p3) for the full
backlog table. Do not start Phase 7 work until the stability declaration
template above is filled in. Paid launch work has its own acceptance gates in
[`COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md) and
[`COMMERCIAL_LAUNCH_READINESS_PACK.md`](./COMMERCIAL_LAUNCH_READINESS_PACK.md).

---

## Historical closure record

The sections below document work closed during the 2026-05-04 through
2026-05-18 stabilization sweeps. They are retained for audit trail; **forward
work is defined in [Implementation phases](#implementation-phases) above.**

### Closed instability surfaces (2026-05-04 through 2026-05-17)

1. **API/worker contract mismatch** — Output APIs use modern `Output` fields;
   cancellation removes current and legacy queue payload shapes; synthesis no
   longer reads missing `Template.slug` / `Template.is_deleted`.
2. **Worker completion persistence gap** — Token-protected callback persists
   PostgreSQL job status + output rows; Redis remains real-time path.
3. **Migration drift** — Alembic revision aligns `outputs` table with live model.
4. **Schema drift in API responses** — Jobs, outputs, callbacks, Studio gallery
   share modern output shape.
5. **Worker image-name drift** — Dash-form `ghcr.io/madfam-org/ceq-worker`.
6. **Studio execution contract drift** — Studio sends `params`; WebSocket appends
   Janua token for `/v1/jobs/{job_id}/stream`.
7. **ArgoCD/kustomize selector mismatch** — Switched from `commonLabels` to
   `labels:` with `includeSelectors: false` (prevented ~7h 502 on 2026-05-04).
8. **NetworkPolicy gaps** — Added allow rules for cloudflared ingress, intra-namespace,
   HTTPS egress, data egress.
9. **Kyverno rejections** — Migration job + worker securityContext aligned.
10. **Migration secret key casing** — Uppercase `DATABASE_URL` / `REDIS_URL`.
11. **ImagePullBackOff on migration job** — Added `ghcr-credentials` pull secret.
12. **No CI test gate** — `.github/workflows/ci.yaml` runs lint + tests on every PR.
13. **OpenAPI exposed in prod concern** — `docs_url=None` when production; verified
    live `/docs` → 404.

### Implementation wave 2026-05-14 — runtime control

Delivered locally and in GitOps:

- Active worker cancellation (Redis control channel, ComfyUI interrupt, durable
  `cancelled`)
- Multi-modal output contract (image, video, audio, model, generic files)
- Completion callback retries + Redis dead-letter (`ceq:jobs:completion:dead`)
- DB idempotency: `uq_outputs_job_storage_uri` via migration
  `20260514_outputs_job_storage_unique`
- Admin API: `/v1/operations/status`, dead-letter list/replay/discard
- Prometheus counters for completions, outputs, cancellations, webhooks
- GitOps: worker digest pinned on every deploy (commit `44f2e0b`, run
  `25850545748`)

### Implementation wave 2026-05-14 — auth + conversion

Delivered and deployed:

- Server-gated Studio routes on `app.ceq.lol` (session cookie required)
- OAuth callback sets httpOnly access/refresh cookies
- `GET /api/auth/session` bootstrap + refresh
- Host split: `ceq.lol` landing, `app.ceq.lol` authenticated app
- Public smoke verifies auth gate after deploy (digest commit `1eaf6a6`)

Partially delivered (Phase 5 remaining):

- `/api/proxy` BFF for REST — done
- WebSocket session migration — done (`resolveStreamAuthToken()`)
- Browser Playwright E2E in CI — done (6 mocked Janua tests; CI job `Studio · Playwright auth`)

### Implementation wave 2026-06-02 — landing conversion

Delivered in code, pending production deploy:

- Public landing rewritten around the core CEQ outcome: repeatable client-ready AI assets without rebuilding ComfyUI graphs
- First-viewport product proof panel shows template inputs, SDK shape, stable URL, credit cost, and cache-hit semantics
- Superpower matrix maps customer pains to CEQ production outcomes
- Simulated landing demo covers Card, Thumbnail, Audio, and 3D Plate flows and demonstrates cache-hit economics
- Pricing CTAs now drive free start, founding-price reservation, and studio pilot intent while paid checkout remains gated
- Buyer-safety section links terms, privacy, acceptable use, retention, and refund routes
- Landing tests cover hero promise, CTA, demo switching, cache-hit state, and legal links

### 2026-05-17 remediation wrap-up

- Observability primitives wired in `infrastructure/k8s/observability.yaml`
- Browser proxy auth hardening for REST workflows
- Remaining at that checkpoint: Janua unblock, secret provisioning, prod GPU
  proof, alert routing confirmation

Key commits referenced in closure cycles:

- `46b3262` — smoke hardening
- `1648ebc` — CI + Next build hardening
- `44f2e0b` — first worker digest-gated GitOps commit
- `1eaf6a6` — Studio auth gate deploy

### 2026-05-18 studio digest guardrail

- Deploy digest `sha256:1a03d7ef5fcc43e9914b970800145ddf38326063dfab5a8eb4a891c5273dbe12`
  for `ceq-studio` crashed immediately with `Cannot find module '/app/server.js'`.
- Production pinned back to healthy digest
  `sha256:20bc96f43554f4abba8c23d12b1bc2e8310f4191e307ddcacfdd5a72dbb6a017`.
- **Follow-up (Phase 4):** Add Studio Docker container smoke to CI/deploy
  workflow before digest commits.

### Completed acceptance criteria (local / code-level)

These are met in the repo and local test matrix. Production proof is tracked in
[Phase 2](#phase-2--production-gpu-runtime-proof-p0).

- `/v1/jobs/{id}/cancel` removes queued payloads (current + legacy shapes)
- `/v1/outputs` and `/v1/jobs/{id}/outputs` use modern `Output` model fields
- Worker completions persist final `Job` status and durable `Output` rows
- Callback endpoint authenticates via shared token; idempotent on replay
- Active cancellation interrupts ComfyUI and reports durable `cancelled`
- Callback failures retry; exhausted payloads dead-lettered
- DB-level `(job_id, storage_uri)` idempotency via migration
- Worker/Studio handle image, video, audio, model, generic file descriptors
- User-provided job webhooks implemented locally (`webhook_url` + HMAC);
  production needs `JOB_WEBHOOK_SECRET` provisioned
- CI regression covers synthesis fallback, queue cancel, callback idempotency,
  modern output fields

### Service scope ownership (reference)

| Scope | Paths | Status |
|-------|-------|--------|
| api-core | `apps/api/src/ceq_api` | Runtime contracts closed; prod smoke open |
| worker | `apps/workers/src/ceq_worker` | Callback + cancel closed; prod GPU smoke open |
| data | `apps/api/src/ceq_api/alembic/` | Migration committed; prod apply verify open |
| infra | `infrastructure/k8s/` | Wired; secrets + alert routing open |
| frontend | `apps/studio/src` | Auth gate + proxy closed; WS + E2E open |

### Files changed during stabilization (reference)

- **apps/api** — `db.session`, `routers.jobs`, `routers.synthesis`,
  `routers.outputs`, `routers.operations`, `config`, alembic migrations
- **apps/workers** — `handler.py`, `queue.py`, `storage.py`, `config.py`,
  `comfyui.py`, `orchestrator.py`
- **infrastructure/k8s** — deployments, `external-secret.yaml`,
  `network-policies.yaml`, `observability.yaml`
- **apps/studio** — `middleware.ts`, auth routes, `/api/proxy`, gallery components
- **scripts** — `production-smoke.sh`, `check-networkpolicy-ports.py`
- **docs** — this file, `PRODUCTION_DEPLOYMENT.md`, `API.md`

---

*Forward work lives in [Implementation phases](#implementation-phases). Do not
add new stability work without assigning it to a phase and acceptance gate.*
