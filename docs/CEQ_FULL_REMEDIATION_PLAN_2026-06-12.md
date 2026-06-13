# CEQ Full Remediation Plan — 2026-06-12

> **Audience:** Engineering, platform operators, product  
> **Status:** Active execution baseline  
> **Supersedes:** Partial session work only; defers to existing truth layer for evidence  
> **Truth layer:** [`DOCS_EVIDENCE_AUDIT_2026-06-02.md`](./DOCS_EVIDENCE_AUDIT_2026-06-02.md), [`CEQ_STABILITY_ROADMAP.md`](./CEQ_STABILITY_ROADMAP.md), [`COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md)

---

## Executive summary

Live audit on **2026-06-12** confirmed CEQ public edge is healthy but **authenticated product value is broken in production**: Janua login succeeds in Studio while the API returns `401 Invalid credentials` because `ceq-api` lacks JWKS/issuer/audience env vars. GPU fulfillment is unproven (`ceq-worker` @ 0 replicas; no orchestrator deployed).

This plan sequences **code → deploy → secrets → smoke → evidence** across five phases. Phases 0–3 have **repo implementation complete** (uncommitted as of this doc). Phases 4–5 are commercial GA and remain planning-only.

| Milestone | Before | After Phase 3 deploy |
|-----------|--------|----------------------|
| Authenticated API | 401 with valid JWT | 200 on `/v1/workflows`, `/v1/credits/balance` |
| Studio UX | False “logged in” | Banner when API auth fails; live template counts |
| GPU golden path | Not proven | Vast orchestrator + external Redis path ready |
| Capped GA demo | ~55% | ~80% (pending prod smoke evidence) |
| Commercial GA | ~45% | Unchanged (~50% after capped GA) |

---

## Root cause register (2026-06-12 live audit)

| ID | Symptom | Root cause | Fix lane |
|----|---------|------------|----------|
| RC-1 | API 401 `"Invalid credentials. Signal corrupted."` with valid Janua JWT | `ceq-api` missing `JANUA_JWKS_URL`, `JANUA_ISSUER`, `JANUA_AUDIENCE=ceq-api` | Phase 0 |
| RC-2 | Studio shows logged-in; jobs/workflows fail | Studio parses JWT locally without signature verify | Phase 2 |
| RC-3 | `ceq-janua-client-secret` ExternalSecret degraded | Vault missing `JANUA_CLIENT_SECRET` | Phase 0 ops |
| RC-4 | Template hub shows wrong counts (12/8/5) | Hardcoded UI vs live API (13 templates, 4/3/3/3) | Phase 2 |
| RC-5 | No GPU job completion | No worker capacity; in-cluster path blocked (no GPU nodes) | Phase 3 |
| RC-6 | Vast workers cannot reach Redis | Internal cluster DNS unreachable from Vast.ai | Phase 3 |
| RC-7 | Billing/credits `--` | Checkout disabled; Dhanam entitlements not funded | Phase 5 |
| RC-8 | Tulana N/A for compute | Tulana is pricing/PMF only | Documented in GPU strategy |

---

## Phase map

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5
 Identity     Secrets      Studio UX    GPU/Vast     Strict       Commercial
 (JWT k8s)    (Vault)      fixes        orchestrator smoke        GA
     │            │            │              │           │            │
     └────────────┴────────────┴──────────────┴───────────┘            │
                    Capped GA demo (~1 week after deploy)              │
                                                                       Paid launch
```

---

## Phase 0 — API identity (P0)

**Goal:** `ceq-api` validates Janua JWTs with audience `ceq-api`.

### Repo changes (done)

| File | Change |
|------|--------|
| `infrastructure/k8s/api-deployment.yaml` | Add `JANUA_JWKS_URL`, `JANUA_ISSUER`, `JANUA_AUDIENCE=ceq-api` |
| `infrastructure/k8s/db-migrate-job.yaml` | Same Janua env for parity |
| `infrastructure/k8s/external-secret.yaml` | `ceq-janua-client-secret` → Vault `JANUA_CLIENT_SECRET` |
| `apps/api/.env.example`, `.env.example` | `JANUA_AUDIENCE=ceq-api` (not `ceq`) |
| `apps/api/tests/test_k8s_manifests.py` | Regression tests |

### Operator actions (required)

1. Populate Vault `secret/ceq` → `JANUA_CLIENT_SECRET`
2. Verify ExternalSecret: `ceq-janua-client-secret` → `Ready=True`
3. Merge + ArgoCD sync
4. Smoke:

```bash
# Obtain JWT from browser session or Janua token endpoint
export CEQ_AUTH_TOKEN='<janua-jwt-with-aud-ceq-api>'
curl -sS -H "Authorization: Bearer $CEQ_AUTH_TOKEN" \
  https://api.ceq.lol/v1/credits/balance | jq .
```

**Done when:** HTTP 200 + balance JSON; Studio banner clears.

---

## Phase 1 — Runtime secrets health (P0)

**Goal:** All ExternalSecrets synced; callback/webhook tokens present.

### Operator checklist

- [ ] `ceq-secrets` ExternalSecret → `Ready=True`
- [ ] `JOB_COMPLETION_CALLBACK_TOKEN` populated
- [ ] `JOB_WEBHOOK_SECRET` populated
- [ ] `GET /v1/operations/status` with admin JWT returns green subsystems

```bash
export CEQ_ADMIN_AUTH_TOKEN="$CEQ_AUTH_TOKEN"
CEQ_RUN_OPERATIONS_STATUS=true \
  CEQ_REQUIRE_OPERATIONS_STATUS=true \
  bash scripts/post-deploy-verify.sh
```

**Done when:** Operations status captured in `ops/evidence/`.

---

## Phase 2 — Studio UX honesty (P1)

**Goal:** UI reflects API truth; template hub uses live data.

### Repo changes (done)

| File | Change |
|------|--------|
| `apps/studio/src/lib/auth.ts` | `probeApiSession()` → `/api/proxy/v1/credits/balance` |
| `apps/studio/src/contexts/auth-context.tsx` | `isApiAuthorized` state + refresh retry |
| `apps/studio/src/components/layout/main-layout.tsx` | Destructive banner when Janua OK but API 401 |
| `apps/studio/src/app/templates/page.tsx` | Live API counts, utility category, recent templates |
| `apps/studio/src/components/quick-actions.tsx` | `+ New` → `/templates`; ⌘K palette |
| `apps/studio/src/components/command-palette.tsx` | `ceq:open-command-palette` event |

**Done when:** Phase 0 deployed; banner absent for admin; template counts match API.

---

## Phase 3 — GPU compute path (P0)

**Goal:** External Vast.ai workers drain Redis DB 14 queue; one golden-path job completes.

**Strategy:** Cross-referenced Tulana (pricing only), internal-devops, solarpunk-foundry, Enclii Furnace PRD. See [`GPU_COMPUTE_STRATEGY.md`](./GPU_COMPUTE_STRATEGY.md) and `internal-devops/decisions/2026-06-12-ceq-gpu-compute-provider-strategy.md`.

### Repo changes (done)

| File | Change |
|------|--------|
| `apps/workers/src/ceq_worker/config.py` | `CEQ_WORKER_REDIS_URL`, `CEQ_WORKER_API_URL` |
| `apps/workers/src/ceq_worker/orchestrator.py` | Inject external URLs into Vast instance env |
| `infrastructure/k8s/worker-orchestrator-deployment.yaml` | CPU `ceq-orchestrator` Deployment |
| `infrastructure/k8s/external-secret.yaml` | `VAST_API_KEY`, `FAL_API_KEY`, `CEQ_WORKER_REDIS_URL` |
| `infrastructure/k8s/worker-deployment.yaml` | Documented blocked @ 0 replicas |
| `docs/GPU_COMPUTE_STRATEGY.md` | Canonical compute doc |

### Operator actions (required)

1. Vault: `VAST_API_KEY`, `CEQ_WORKER_REDIS_URL` (public/Tailscale Redis DB 14)
2. Optional: `FAL_API_KEY` for ≤24GB image templates
3. ArgoCD sync → `ceq-orchestrator` Running
4. Golden-path smoke:

```bash
source ops/smoke-config.env.example  # copy and fill CEQ_AUTH_TOKEN
bash scripts/post-deploy-verify.sh --gpu
```

**Canonical template IDs (prod):**

| Template | UUID | Use |
|----------|------|-----|
| FLUX SCHNELL | `d8b30c7e-4501-493f-94c7-5223d7777afb` | Fast golden-path smoke |
| FLUX.1 DEV | `94df20ca-280f-43a1-baa9-1c8b3f4eae48` | Quality image smoke |

**Done when:** Job completes; R2 output URL; gallery shows artifact. Evidence in `ops/evidence/YYYY-MM-DD-gpu-golden-path.md`.

---

## Phase 4 — Strict smoke + CI gates (P1)

**Goal:** Every release candidate passes authenticated + public smoke.

### Repo changes (done)

| File | Change |
|------|--------|
| `scripts/post-deploy-verify.sh` | Bundles public + auth + optional GPU checks |
| `ops/smoke-config.env.example` | Canonical env template |
| `.github/workflows/post-deploy-smoke.yaml` | `workflow_dispatch` with `CEQ_AUTH_TOKEN` secret |

### Operator actions

- [ ] Add GitHub secret `CEQ_AUTH_TOKEN` (Janua JWT or refreshable service account)
- [ ] Add GitHub secret `CEQ_ADMIN_AUTH_TOKEN` (optional, defaults to auth token)
- [ ] Run post-deploy workflow after each prod sync

**Done when:** Strict smoke green in CI; branch protection optionally requires workflow.

---

## Phase 5 — Commercial GA (P1–P2, not in this sprint)

Tracked in [`COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md):

| Item | Owner | Blocker |
|------|-------|---------|
| Dhanam checkout + entitlements | Product + API | No funded pilot |
| Credit debit/refund on GPU/render | API | Feature flags exist; needs billing source |
| Plan-aware quotas | API + Platform | Role-only caps today |
| Alert routing + on-call drill | Platform | Enclii metrics placeholder |
| Legal review | Product + Legal | Docs drafted, not signed off |
| Furnace migration | Enclii + CEQ | Gateway `:4210` not deployed |

---

## Execution schedule

| Week | Focus | Exit criteria |
|------|-------|---------------|
| W0 (now) | Merge Phases 0–3 code; Vault secrets | PR merged; ExternalSecrets green |
| W0+1d | Deploy; auth smoke | `credits/balance` 200; operations status captured |
| W0+2d | Orchestrator + Vast | Queue drains; one FLUX SCHNELL output |
| W1 | Strict smoke in CI; capped GA declaration | Evidence pack complete |
| W2+ | Phase 5 commercial tracks | Separate program |

---

## Smoke matrix (operator quick reference)

| Command | Scope | Credentials |
|---------|-------|-------------|
| `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh` | Public edge | None |
| `bash scripts/post-deploy-verify.sh` | Public + auth session checks | `CEQ_AUTH_TOKEN` |
| `bash scripts/post-deploy-verify.sh --strict` | + operations status + cancel + credits | Admin token |
| `bash scripts/post-deploy-verify.sh --gpu` | + template job golden path | Token + Vast running |
| `scripts/capture-public-endpoint-matrix.sh` | CSV evidence | None |

---

## Risk register

| Risk | Mitigation |
|------|------------|
| Vault secret gap persists | Block deploy PR until ExternalSecret Ready |
| Public Redis exposure for Vast | TLS + auth; Tailscale preferred; Enclii adapter gap recorded |
| Vast spend runaway | `CEQ_MAX_HOURLY_SPEND=5.0` on orchestrator |
| JWT audience mismatch | Manifest test locks `ceq-api` |
| False Studio login state | `isApiAuthorized` probe (Phase 2) |

---

## Evidence requirements

Each phase closure requires a row in `ops/evidence/`:

```
ops/evidence/YYYY-MM-DD-<phase>-<slug>.md
```

Minimum fields: timestamp (UTC), operator, commands run, HTTP status codes, artifact URLs, ArgoCD sync revision.

---

## Related documents

- [`GPU_COMPUTE_STRATEGY.md`](./GPU_COMPUTE_STRATEGY.md)
- [`GA_DEMO_DEFINITION.md`](./GA_DEMO_DEFINITION.md)
- [`JANUA_OPERATOR.md`](./JANUA_OPERATOR.md)
- [`PLATFORM_AGENT_HANDOFFS.md`](./PLATFORM_AGENT_HANDOFFS.md)
- `internal-devops/decisions/2026-06-12-ceq-gpu-compute-provider-strategy.md`
