# CEQ GPU Compute Strategy

> **Last updated:** 2026-06-12  
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
Studio/API ──LPUSH──► Redis DB14 (ceq:jobs:pending)
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
  ceq-orchestrator    (blocked)          fal.ai (optional)
  CPU pod in ceq      ceq-worker         API-side router in
  scales Vast.ai      KEDA @ 0           workers package only
         │
         ▼
  Vast.ai instances (ghcr.io/madfam-org/ceq-worker)
  run: python -m ceq_worker.queue
         │
         └──► R2 outputs + POST /v1/jobs/{id}/outputs/report
```

### Critical: external worker connectivity

Vast.ai instances run **outside** the k3s cluster. They cannot reach internal URLs like `redis.data.svc.cluster.local` or `http://ceq-api.ceq.svc.cluster.local`.

| Variable | Orchestrator (in-cluster) | Vast worker (external) |
|----------|---------------------------|-------------------------|
| `REDIS_URL` | Internal cluster Redis | **`CEQ_WORKER_REDIS_URL`** — must be reachable from public internet (TLS + auth) |
| `API_URL` | N/A | **`https://api.ceq.lol`** via `CEQ_WORKER_API_URL` |

The orchestrator Deployment sets `CEQ_WORKER_*` overrides; if `CEQ_WORKER_REDIS_URL` is unset, it falls back to `REDIS_URL` (works only for in-cluster workers).

---

## Deployment paths

### Path A — Vast.ai + in-cluster orchestrator (recommended)

1. Store `VAST_API_KEY` in Vault → `ceq-secrets` / dedicated secret
2. Configure **`CEQ_WORKER_REDIS_URL`** to a Vast-reachable Redis endpoint (operator break-glass until Enclii adapter)
3. Deploy `infrastructure/k8s/worker-orchestrator-deployment.yaml` via GitOps
4. Verify: `kubectl -n ceq logs deployment/ceq-orchestrator`
5. Submit authenticated template job; watch queue drain and gallery populate

### Path B — Manual Vast instance

Use `apps/workers/scripts/deploy-vast.sh` with exported `REDIS_URL`, `R2_*`, and public `API_URL`.

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

# Ensure orchestrator is running and Vast workers can reach Redis
bash scripts/production-smoke.sh
```

Evidence: `ops/evidence/YYYY-MM-DD-gpu-golden-path.md`

---

## Tulana integration (pricing only)

| Tulana surface | CEQ use |
|----------------|---------|
| `GET /api/v1/pmf/products/ceq/status` | InterestGate / checkout gating |
| Dhanam catalog mirror (`ceq__pro_artist`, `ceq__studio`) | Billing tier display |
| Competitor benchmarks (RunPod, fal.ai, Replicate) | Credit pricing pressure — not routing |

Credit tiers (provisional, low confidence): Creator 100/mo free, Pro Artist 349 MXN, Studio 1,299 MXN per Tulana ecosystem pricing decision.
