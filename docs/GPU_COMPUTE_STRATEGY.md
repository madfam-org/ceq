# CEQ GPU Compute Strategy

> **Last updated:** 2026-08-24  
> **Audience:** CEQ operators, platform engineers  
> **Cross-references:** [VAST_AI_SETUP.md](./VAST_AI_SETUP.md), [GA_DEMO_DEFINITION.md](./GA_DEMO_DEFINITION.md), Enclii [`PRD_FURNACE.md`](../../enclii/docs/architecture/PRD_FURNACE.md), solarpunk-foundry [`DOGFOODING_GUIDE.md`](../../solarpunk-foundry/docs/DOGFOODING_GUIDE.md)

---

## Summary

| Provider | Role | Status | When to use |
|----------|------|--------|-------------|
| **Vast.ai** | Primary ComfyUI GPU (instance-based) | **Production path today** | Full workflows, video, 3D, custom graphs |
| **fal.ai** | Supplementary serverless image jobs | Optional (`FAL_API_KEY`) | Social/utility templates ≤24GB VRAM |
| **In-cluster KEDA worker** | Self-hosted queue consumer | **Blocked** (no GPU nodes) | After Hetzner GPU hardware + device plugin |
| **Furnace (Enclii)** | Future sovereign GPU layer | PRD only | After Gateway `:4210` ships on GEX44 |

**Tulana** (`tulana.madfam.io`) informs **pricing, PMF, and paywall timing** — not compute routing. Competitor benchmarks (RunPod, Replicate, fal.ai) are pricing inputs, not execution backends.

### External workers connect over HTTPS, not Redis

External GPU workers lease jobs through an authenticated HTTPS API on ceq-api
(`/v1/worker/*`, Janua `ceq:worker` scope). The job queue stays cluster-internal.
Publishing Redis DB14 to the public internet — previously a prerequisite for the
Vast path — is **demoted to a legacy alternative** and should not be used for new
deployments. See [Critical: external worker connectivity](#critical-external-worker-connectivity).

**Operator GPU-unblock list (was three items, now two):**

| # | Item | Status |
|---|------|--------|
| 1 | `VAST_API_KEY` in Vault | Operator action |
| 2 | Scale orchestrator (`worker-orchestrator-deployment.yaml` via GitOps) | Operator action |
| ~~3~~ | ~~Publicly reachable Redis endpoint~~ | **Eliminated** by the lease API |

Item 2 now also carries the Janua worker-client credentials (`CEQ_WORKER_CLIENT_ID` /
`CEQ_WORKER_CLIENT_SECRET`), registered the same way as any other MADFAM service
principal — a Janua-side registration, not a new piece of exposed infrastructure.

---

## Ecosystem alignment

### solarpunk-foundry / PORT_ALLOCATION

- CEQ API: **5800**, Studio: **5801**, workers: **5810–5819**, WebSocket: **5820**
- Redis **DB 14** — CEQ job queue (`ceq:jobs:pending`)
- Redis **DB 15** — reserved for Furnace (future Enclii extension)

### internal-devops posture

- Hetzner cluster has **no GPU nodes** today; `ceq-worker` Deployment at **0 replicas** is intentional
- Procurement tracker defers GPU SKU; Enclii GPU manifests exist but are disabled
- **Implicit decision (now formalized):** Vast.ai interim → Furnace on GEX44 → optional in-cluster KEDA

See also: [`internal-devops/decisions/2026-06-12-ceq-gpu-compute-provider-strategy.md`](../../internal-devops/decisions/2026-06-12-ceq-gpu-compute-provider-strategy.md)

### Furnace (Enclii)

- Planned ports **4210–4215** on Hetzner GEX44 (~$220/mo vs ~$316/mo RunPod 4090)
- CEQ `FurnaceProvider` stub exists; **do not point production at Furnace until gateway is live**
- `FURNACE_API_URL` in k8s: `http://furnace-gateway.enclii.svc.cluster.local:4210`

---

## Production architecture (today)

```
Studio/API ──LPUSH──► Redis DB14 (ceq:jobs:pending)   [CLUSTER-INTERNAL]
                           │
         ┌─────────────────┼─────────────────┬───────────────────────┐
         ▼                 ▼                 ▼                       ▼
  ceq-orchestrator    (blocked)          fal.ai (optional)   ceq-api /v1/worker/*
  CPU pod in ceq      ceq-worker         API-side router     HTTPS job-lease API
  scales Vast.ai      KEDA @ 0           in workers pkg      (ceq:worker scope)
         │                                                           │
         ▼                                                           ▼
  Vast.ai instances (ghcr.io/madfam-org/ceq-worker)  ──lease/heartbeat/complete──┘
  run: python -m ceq_worker.queue  (dispatches to lease mode when CEQ_LEASE_URL set)
         │
         └──► R2 outputs + completion report
```

### Critical: external worker connectivity

Vast.ai instances run **outside** the k3s cluster. They cannot reach internal URLs like `redis.data.svc.cluster.local` or `http://ceq-api.ceq.svc.cluster.local`.

There are two ways to bridge that gap. **The lease API is the supported one.**

| | **Lease API (default)** | Public Redis (legacy) |
|---|---|---|
| Transport | HTTPS to `https://api.ceq.lol/v1/worker/*` | Direct Redis protocol |
| Public surface | The API that is *already* public | **Redis DB14, newly exposed** |
| AuthN | Janua `client_credentials` JWT, RS256, ~1h | Redis password |
| AuthZ | Dedicated `ceq:worker` scope, per-job leases | All-or-nothing: full queue access |
| Blast radius if the credential leaks | Lease jobs for the lease TTL; revoke the Janua client | Read/write **every** tenant's job payloads, and the shared DB14 keyspace |
| Rotation | Re-mint automatically; revoke centrally in Janua | Manual password rotation + redeploy of every instance |
| Status | **Recommended** | Legacy alternative; use only if the lease API is unavailable |

Exposing Redis publicly was always the weak point of the Vast path: it puts an
unauthenticated-by-design datastore holding every tenant's job payloads on the
public internet, secured by one static password, with no per-worker scoping and
no revocation story. The lease API removes that requirement outright.

### Lease API contract

| Endpoint | Purpose |
|----------|---------|
| `POST /v1/worker/lease` | Claim the next pending job; opens a visibility-timeout lease. `204` when the queue is empty. |
| `POST /v1/worker/jobs/{id}/heartbeat` | Extend the lease; also surfaces `cancel_requested`. |
| `POST /v1/worker/jobs/{id}/complete` | Land outputs + metadata (same persistence path as Redis mode). |
| `POST /v1/worker/jobs/{id}/fail` | Requeue if attempts remain, else dead-letter. |
| `POST /v1/worker/jobs/{id}/upload-url` | Presigned R2 PUT, for workers without their own R2 credentials. |

**Interop guarantee.** Lease claims run `RPOPLPUSH ceq:jobs:pending →
ceq:jobs:processing` inside a Lua script — the same tail-pop a Redis worker's
`BRPOPLPUSH` performs on the same two lists. Redis arbitrates; exactly one
claimant wins any payload. In-cluster Redis workers and external HTTPS workers
can therefore run **simultaneously** against one queue with no double-processing,
which is what makes a gradual migration possible.

**Crash recovery.** A lease is a visibility timeout, not a held lock. A worker
that dies stops heartbeating; once `WORKER_LEASE_TTL_SECONDS` elapses the job is
moved back to `pending` and is claimable again. Delivery is therefore
at-least-once: outputs upsert on `(job_id, storage_uri)`, so a re-run overwrites
rather than duplicates. Past `WORKER_LEASE_MAX_ATTEMPTS` the payload is
dead-lettered to `ceq:jobs:lease:dead` instead of cycling forever.

**Scope split.** `ceq:worker` is deliberately *not* `ceq:render`. `ceq:render`
is the submit capability held by batch drivers; `ceq:worker` is the execute
capability held by GPU boxes. Neither implies the other, so a leaked batch-driver
secret cannot read and complete other tenants' jobs, and a compromised Vast
instance cannot enqueue billable work.

### Worker environment

| Variable | Orchestrator (in-cluster) | Vast worker (external, lease mode) |
|----------|---------------------------|-------------------------------------|
| `REDIS_URL` | Internal cluster Redis | **not set** — lease mode never contacts Redis |
| `CEQ_LEASE_URL` | N/A | `https://api.ceq.lol` |
| `CEQ_WORKER_CLIENT_ID` / `CEQ_WORKER_CLIENT_SECRET` | N/A | Janua confidential client granted `ceq:worker` |
| `CEQ_WORKER_API_URL` | N/A | `https://api.ceq.lol` |

`ceq_worker.queue:main` dispatches on configuration: with `CEQ_LEASE_URL` plus
both credentials it runs the lease loop; otherwise it runs the unchanged Redis
loop. In-cluster workers need no change.

---

## Deployment paths

### Path A — Vast.ai + in-cluster orchestrator (recommended)

1. Store `VAST_API_KEY` in Vault → `ceq-secrets` / dedicated secret
2. Register a Janua confidential client for the worker fleet, granted the
   **`ceq:worker`** scope with audience `ceq-api`; store its
   `CEQ_WORKER_CLIENT_ID` / `CEQ_WORKER_CLIENT_SECRET`
3. Deploy `infrastructure/k8s/worker-orchestrator-deployment.yaml` via GitOps
   with `CEQ_LEASE_URL=https://api.ceq.lol` in the injected worker env
4. Verify: `kubectl -n ceq logs deployment/ceq-orchestrator`
5. Submit authenticated template job; watch queue drain and gallery populate

**Redis is no longer part of this path.** `CEQ_WORKER_REDIS_URL` is retained only
for Path B-legacy below.

### Path B — Manual Vast instance (lease mode)

Use `apps/workers/scripts/deploy-vast.sh` with exported `CEQ_LEASE_URL`,
`CEQ_WORKER_CLIENT_ID`, `CEQ_WORKER_CLIENT_SECRET`, `R2_*`, and public `API_URL`.

### Path B-legacy — Manual Vast instance over public Redis

Retained for break-glass only, and only when the lease API is unreachable.
Requires `CEQ_WORKER_REDIS_URL` pointing at a publicly reachable Redis (TLS +
auth) — i.e. it reintroduces exactly the exposure the lease API removes. Prefer
Path B; if you use this, record it as an incident-grade deviation.

### Path C — In-cluster KEDA worker (future)

Prerequisites:

1. Hetzner GEX44 (or equivalent) joined to k3s
2. `enclii/infra/k8s/base/gpu/nvidia-device-plugin.yaml` enabled
3. `ceq-models-pvc` provisioned
4. Scale `ceq-worker` via KEDA ScaledObject (already in manifest)

### Path D — Furnace (future)

1. Enclii ships `furnace-gateway` Phase 1–2
2. Set `GPU_PROVIDER=furnace`, validate `/health` on `:4210`
3. Reconcile CEQ `FurnaceProvider` API with PRD `/v1/endpoints` contract

---

## Provider selection matrix

| Workload | VRAM | Provider |
|----------|------|----------|
| FLUX SCHNELL (4-step) | 16GB | Vast.ai or fal.ai |
| FLUX DEV / SD3 / video | 16–24GB+ | Vast.ai |
| Hunyuan Video | 24GB+ | Vast.ai |
| 3D (TriposR, CRM) | 16–20GB | Vast.ai; fal.ai for TriposR if configured |
| Deterministic `/v1/render/*` | CPU | ceq-api (no GPU worker) |

---

## Golden-path smoke (after API JWT fix)

```bash
export CEQ_AUTH_TOKEN='<janua-jwt>'
export CEQ_TEMPLATE_ID='d8b30c7e-4501-493f-94c7-5223d7777afb'  # FLUX SCHNELL
export CEQ_TEMPLATE_PARAMS_JSON='{"prompt":"golden path smoke","width":512,"height":512}'

# Ensure the orchestrator is running and Vast workers hold ceq:worker credentials
bash scripts/production-smoke.sh
```

Lease-path spot check (no Redis exposure required):

```bash
# Mint a worker token, then confirm the lease surface answers.
# 204 = queue empty (healthy). 200 = a job was leased. 403 = wrong scope.
TOKEN=$(curl -s -X POST https://auth.madfam.io/api/v1/oauth/token \
  -d grant_type=client_credentials \
  -d client_id="$CEQ_WORKER_CLIENT_ID" \
  -d client_secret="$CEQ_WORKER_CLIENT_SECRET" \
  -d scope='ceq:worker' | jq -r .access_token)

curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST https://api.ceq.lol/v1/worker/lease \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"worker_id":"smoke-check"}'
```

A `ceq:render` token must return **403** here — that is the scope split working.

Evidence: `ops/evidence/YYYY-MM-DD-gpu-golden-path.md`

---

## Tulana integration (pricing only)

| Tulana surface | CEQ use |
|----------------|---------|
| `GET /api/v1/pmf/products/ceq/status` | InterestGate / checkout gating |
| Dhanam catalog mirror (`ceq__pro_artist`, `ceq__studio`) | Billing tier display |
| Competitor benchmarks (RunPod, fal.ai, Replicate) | Credit pricing pressure — not routing |

Credit tiers (provisional, low confidence): Creator 100/mo free, Pro Artist 349 MXN, Studio 1,299 MXN per Tulana ecosystem pricing decision.
