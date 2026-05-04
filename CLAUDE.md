# CLAUDE.md - ceq Repository Instructions

> **ceq** — Creative Entropy Quantized
> *The Skunkworks Terminal for the Generative Avant-Garde*

## Project Overview

**ceq** is a ComfyUI wrapper designed for MADFAM's content production needs. It wraps the raw power of ComfyUI with a streamlined, hacker-centric interface while maintaining full access to the underlying node system.

| Property | Value |
|----------|-------|
| **Domain** | ceq.lol |
| **Port Block** | 5800-5899 |
| **Status** | Live (api.ceq.lol + ceq.lol serving; render pipeline shipped 2026-04-19) |
| **Philosophy** | Wrestling order from the chaos of latent space |

## Current Deployment Status (2026-04-19)

| Component | Status | Notes |
|-----------|--------|-------|
| ceq.lol (studio) | Live | 2 pods Running in `ceq` namespace |
| api.ceq.lol (api) | Live | 2 pods Running |
| `/v1/render/*` pipeline | Shipped | Card renderer + R2 cache + @ceq/sdk (62fcfe9) |
| Janua OAuth Client | Registered | `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk` |
| Cloudflare R2 Bucket | Live | `ceq-assets` — render cache under `render/{template}/{hash}.{ext}` |
| Cloudflare Tunnel | Configured | Routes for ceq.lol, api.ceq.lol, ws.ceq.lol |

## Asset-pillar surface (shipped 2026-04-19)

`POST /v1/render/card`, `/thumbnail`, `/audio`, `/3d`, `GET /v1/render/templates` — deterministic, content-addressed, R2-cached. Identical inputs always return the same URL. See `apps/api/README.md#render-generative-assets` for the full contract.

Built-in templates (as of 2026-04-19):

| Endpoint | Template | Output | Notes |
|---|---|---|---|
| `/v1/render/card` | `card-standard` | 512×768 PNG | Pillow-rendered card thumbnail |
| `/v1/render/audio` | `tone-beep` | 16-bit PCM WAV @ 22.05kHz | Parametric sine + ADSR envelope (stdlib) |
| `/v1/render/3d` | `card-plate` | GLB (glTF 2.0 binary) | Parametric rounded-rectangle plate (stdlib writer) |

Client: `@ceq/sdk` (`packages/sdk/`) — `CeqClient.renderCard/renderAudio/render3D({...})` for JS/TS consumers. First external consumer: Rondelio's stratum-tcg cartridge (`services/simulator/cartridges/stratum-tcg/scripts/generate_art.py`, `--provider ceq`).

## Architecture

```
ceq/
├── apps/
│   ├── studio/       # Next.js 14 frontend (port 5801)
│   ├── api/          # FastAPI orchestration (port 5800)
│   └── workers/      # ComfyUI GPU workers (ports 5810-5819)
├── packages/
│   ├── ui/           # Shared ceq UI components
│   ├── workflow-types/ # TypeScript workflow types
│   └── sdk/          # ceq SDK for integrations
├── templates/
│   ├── social/       # Social media content workflows
│   ├── video/        # Video clone workflows
│   └── 3d/           # 3D rendering workflows
├── infrastructure/
│   └── k8s/          # Kubernetes manifests
└── docs/
    ├── PRD.md        # Product Requirements Document
    └── PRODUCTION_DEPLOYMENT.md  # Deployment guide
```

## Tech Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| Frontend | Next.js 14, shadcn/ui, Zustand | Dark mode only |
| API | FastAPI, SQLAlchemy, Pydantic v2 | Python 3.11+ |
| Workers | Python, comfy_runner | Vast.ai (current), Furnace (future) |
| Queue | Redis | Job queue, real-time updates (DB 14) |
| Database | PostgreSQL | Via Enclii shared infra |
| Storage | Cloudflare R2 | Assets and outputs (`ceq-assets` bucket) |
| Auth | Janua | @janua/react-sdk |
| Hosting | Enclii | k3s on Hetzner via Cloudflare Tunnel |

## Dependencies

### Internal MADFAM Services

| Service | Domain | Purpose |
|---------|--------|---------|
| Janua | auth.madfam.io | Authentication and user management |
| Enclii | app.enclii.dev | Platform hosting and deployment |
| Furnace | (future) | GPU compute scheduling |

### External Services

| Service | Purpose | Status |
|---------|---------|--------|
| Cloudflare R2 | Asset and output storage | Ready (`ceq-assets`) |
| Redis Sentinel | Job queue and caching (DB 14) | Pending infra deploy |
| PostgreSQL | Metadata storage | Pending (Ubicloud) |
| Vast.ai | GPU workers (current) | API key required |

## Development Commands

```bash
# Install dependencies
pnpm install

# Run studio locally (port 5801)
pnpm --filter @ceq/studio dev

# Run API locally (port 5800)
cd apps/api
source .venv/bin/activate
uvicorn ceq_api.main:app --port 5800 --reload

# Run worker (requires GPU and Vast.ai API key)
cd apps/workers
python -m ceq_worker.orchestrator

# Build all
pnpm build

# Type check
pnpm typecheck
```

## Authentication Configuration

### Production OAuth Client (Registered 2025-12-10)

| Property | Value |
|----------|-------|
| **Client Name** | CEQ Studio |
| **Client ID** | `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk` |
| **Grant Types** | authorization_code, refresh_token |
| **Scopes** | openid, profile, email |
| **Redirect URIs** | `https://ceq.lol/auth/callback`, `http://localhost:5801/auth/callback` |

### Usage in Code

```typescript
// apps/studio - JanuaProvider configuration
<JanuaProvider
  domain="auth.madfam.io"
  clientId="jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk"
  redirectUri="https://ceq.lol/auth/callback"
/>
```

## Environment Variables

### API (apps/api/.env)
```bash
DATABASE_URL=postgresql+asyncpg://ceq:PASSWORD@HOST:5432/ceq_production
REDIS_URL=redis://:PASSWORD@redis-0.redis-headless.enclii-production.svc.cluster.local:6379/14
R2_ENDPOINT=https://12f1353f7819865c56161ce00297668e.r2.cloudflarestorage.com
R2_ACCESS_KEY=51844af3c4cbda516895116372ec3b38
R2_SECRET_KEY=<from-secrets.prod.yaml>
R2_BUCKET=ceq-assets
JANUA_URL=https://api.janua.dev
```

### Studio (apps/studio/.env.local)
```bash
NEXT_PUBLIC_API_URL=https://api.ceq.lol
NEXT_PUBLIC_WS_URL=wss://ws.ceq.lol
NEXT_PUBLIC_JANUA_DOMAIN=auth.madfam.io
NEXT_PUBLIC_JANUA_CLIENT_ID=jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk
```

## Key Files

| File | Purpose |
|------|---------|
| `apps/api/src/ceq_api/main.py` | FastAPI entrypoint |
| `apps/studio/app/layout.tsx` | Root layout with providers |
| `apps/workers/src/ceq_worker/handler.py` | GPU job handler |
| `infrastructure/k8s/secrets.prod.yaml` | Production secrets template |
| `infrastructure/k8s/kustomization.yaml` | K8s deployment manifest |

## Code Conventions

### Python (API + Workers)

```python
# FastAPI patterns
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])

class WorkflowCreate(BaseModel):
    name: str
    workflow_json: dict

@router.post("/")
async def create_workflow(data: WorkflowCreate, user: User = Depends(get_current_user)):
    ...
```

### TypeScript (Studio)

```typescript
// Next.js 14 app router patterns
// File: apps/studio/app/workflows/page.tsx
import { WorkflowList } from '@/components/workflow-list';
import { getWorkflows } from '@/lib/api';

export default async function WorkflowsPage() {
  const workflows = await getWorkflows();
  return <WorkflowList workflows={workflows} />;
}
```

### UI Patterns

- **Dark mode only**: No light mode toggle
- **Keyboard-first**: All primary actions have shortcuts
- **Terminal aesthetic**: Monospace fonts, minimal chrome

### Brand Voice in Code

```typescript
// Loading states
const LOADING_MESSAGES = [
  "Quantizing entropy...",
  "Traversing latent space...",
  "Distilling chaos...",
];

// Success states
const SUCCESS_MESSAGES = [
  "Signal acquired.",
  "Materialized.",
  "Entropy contained.",
];

// Error states
const ERROR_MESSAGES = [
  "Chaos won this round. Retry?",
  "Latent space turbulence detected.",
  "Signal lost in the noise.",
];
```

## Kubernetes Deployment

### Production deploys: GitOps via ArgoCD (since 2026-04-28, ceq#16)

CEQ deploys through the same auto-digest GitOps loop as the rest of the
MADFAM ecosystem. `.github/workflows/deploy.yaml` builds + pushes images
to GHCR, resolves each manifest-list digest via
`docker buildx imagetools inspect` (NOT `docker manifest inspect | jq`
— that returns null on multi-arch, see enclii#136), then commits the
new digests to `infrastructure/k8s/kustomization.yaml` as
`madfam-deploy-bot`. ArgoCD's `ceq-services` application picks up the
new digests within ~3 min.

**No `kubectl apply` from CI.** ARC runner pods are NetworkPolicy-isolated
from the kube-apiserver (verified 2026-04-28); direct cluster access from
inside a runner returns exit 7. The GitOps loop is the only deploy path.

**Image-name convention:** all three production images use dash-form:
`ghcr.io/madfam-org/ceq-{api,studio,worker}`. Earlier manifests had a
mix (`ghcr.io/madfam/ceq-api`, `ghcr.io/madfam-org/ceq/studio`); fixed
to dash-form in the GitOps refactor PR. New manifests should match.

**Database migrations** run as a Job with `argocd.argoproj.io/hook: PreSync`
+ `hook-delete-policy: BeforeHookCreation`, so each ArgoCD sync runs
`alembic upgrade head` before the Deployments roll. `seed-templates-job.yaml`
is a manual one-shot, intentionally excluded from the kustomize bundle.

### Bootstrap (first-time only)

```bash
# Namespace + secrets are operator-only; runners can't reach the API.
ssh ssh.madfam.io
sudo k3s kubectl apply -f infrastructure/k8s/namespace.yaml
sudo k3s kubectl apply -f infrastructure/k8s/secrets.local.yaml
```

After that, ArgoCD owns the rollout.

### Manual one-shots (operator)

```bash
# Re-seed templates after a fresh DB:
ssh ssh.madfam.io
sudo k3s kubectl apply -f infrastructure/k8s/seed-templates-job.yaml

# Force a re-migration (delete + ArgoCD will recreate the PreSync Job):
sudo k3s kubectl -n ceq delete job ceq-db-migrate
```

### Verify

```bash
ssh ssh.madfam.io
sudo k3s kubectl -n ceq get pods
sudo k3s kubectl -n ceq logs deployment/ceq-api
```

## Important Notes

1. **ComfyUI Integration**: Uses `comfy_runner` for headless execution, not the ComfyUI web UI
2. **GPU Scheduling**: Workers run on Vast.ai (current) or Furnace (future), never direct GPU access
3. **Asset Storage**: All models, outputs, and assets are stored in R2 (`ceq-assets` bucket)
4. **Real-time Updates**: Job progress via WebSocket on port 5820
5. **Redis DB**: CEQ uses Redis DB 14 per PORT_ALLOCATION.md

## Troubleshooting

### API not starting
```bash
kubectl logs -n ceq deployment/ceq-api
```

### Database connection issues
```bash
# Verify DATABASE_URL format - must use asyncpg:
# postgresql+asyncpg:// (not postgres://)
```

### Auth callback not working
1. Verify redirect URI in Janua matches exactly
2. Check CORS allowed origins in API
3. Verify client_id matches: `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk`

### Cloudflared tunnel issues
```bash
kubectl logs -n ceq deployment/cloudflared
```

## Pricing + PMF

- **Pricing source-of-truth**: `internal-devops/decisions/2026-04-25-tulana-ecosystem-pricing.md`. CEQ tiers per Tulana intel: Creator $0 (100 credits/mo) / Pro Artist 349 MXN (2K credits) / Studio 1,299 MXN (10K credits). **Confidence: low** — DeepInfra inference cost basis is volatile, so InterestGate is the active gating pattern (ceq#11) rather than a paywall. Locks in via PMF Score per RFC 0013.
- **Monetization gating**: `apps/api/src/ceq_api/routers/interest.py` + `apps/studio/src/components/InterestGate.tsx`. Premium-tagged templates (`Template.tags` includes 'pro' or 'premium') show overlay InterestGate for free users; data captured in `feature_interest` table → CRM webhook → Phyne-CRM. Switches to checkout when `recommended_action` from Tulana flips.
- **PMF measurement**: per RFC 0013, NPS + Sean Ellis + retention via `@madfam/pmf-widget` → Tulana `/v1/pmf/*` endpoints.

## Related Documentation

- [README.md](./README.md) - Project overview and quick start
- [docs/PRD.md](./docs/PRD.md) - Full product requirements
- [docs/PRODUCTION_DEPLOYMENT.md](./docs/PRODUCTION_DEPLOYMENT.md) - Deployment checklist
- [Enclii CLAUDE.md](../enclii/CLAUDE.md) - Platform infrastructure

## Known Issues — Audit 2026-04-23

See `/Users/aldoruizluna/labspace/claudedocs/ECOSYSTEM_AUDIT_2026-04-23.md` for the full ecosystem audit.

- ~~**🔴 R1: Cloudflare tunnel token committed in plaintext**~~ — Closed 2026-04-25. The `ceq-prod` tunnel (id `0de376f0-…`) was deleted on the Cloudflare side on 2026-04-09; ceq.lol / api.ceq.lol / ws.ceq.lol now route through the main `enclii-prod` platform tunnel. The token in git was already non-functional. Removed `infrastructure/k8s/cloudflared.yaml` to eliminate the leak surface. Duplicate in `.claude/settings.local.json` is operator-local + also dead.
- ~~**🔴 T1: No CI test gate**~~ — Fixed 2026-04-23: `.github/workflows/ci.yaml` runs lint + typecheck + unit tests for api / workers / studio on every PR. Configure Branch Protection on `main` to require these checks before merge.
- **🟠 H9: OpenAPI docs likely exposed in prod** — verify `docs_url` is None when `env == "production"` on all FastAPI entrypoints.

## Known Issues — Stabilization Sweep 2026-05-04

A multi-hour stabilization run on 2026-05-04 closed several ceq-side ArgoCD-sync bugs and tightened the deploy chain. See `internal-devops/runbooks/2026-05-03-builder-upgrade-ccx33.md` for the broader infra context (CCX33 builder swap that started the same session).

- ~~**🔴 ArgoCD ceq-services pointed at deleted manifest path**~~ — Closed 2026-05-04 via enclii#192. The repo had moved manifests from `infra/k8s/production/` to `infrastructure/k8s/` in PR ceq#20 but ArgoCD's project config still pointed at the old path → `ComparisonError: app path does not exist`. Updated to track `infrastructure/k8s/`.
- ~~**🔴 db-migrate-job blocked by Kyverno**~~ — Closed 2026-05-04 via ceq#24, ceq#25. Migration Job lacked pod-level + container-level securityContext (Kyverno `restrict-capabilities` + `block-host-ports`) and the `ceq` namespace was missing the `enclii.dev/type: application` exemption label. Fixed both.
- ~~**🔴 Migration secret keys lowercase**~~ — Closed 2026-05-04 via ceq#27. Job used `database-url` / `redis-url` from `ceq-secrets`, but keys live there UPPERCASE (`DATABASE_URL`, `REDIS_URL`). studio-deployment uses `envFrom: secretRef` which is case-preserving so it worked; the migration Job using `secretKeyRef.key` did not. Migration now uses uppercase keys to match the rest of the manifest.
- ~~**🟠 ImagePullBackOff on private dash-form image**~~ — Closed 2026-05-04 via ceq#26. Migration Job didn't carry `imagePullSecrets: [ghcr-credentials]` so the GHCR pull returned 401. Studio + API deployments already had this; migration Job inherited the same secret.
- ~~**🟠 ceq.lol 502 after pods running**~~ — Closed 2026-05-04 via ceq#28. The `ceq` namespace had `default-deny-egress` + `default-deny-ingress` from the enclii onboarding bundle but no allow rules for cloudflared → ceq pods. Added 4 NPs: `allow-cloudflared-ingress` (ports 80, 5800, 5801, 8000), `allow-intra-namespace`, `allow-https-egress`, `allow-data-egress`. ceq.lol responded 200 within seconds.
- ~~**🟠 ArgoCD ceq-services Degraded — Service ports + worker SC**~~ — Closed 2026-05-04 via ceq#29. Live cluster ran `port: 80 → targetPort: 5800/5801` (manually patched during the cloudflared work) but source declared `port: 5800/5801`. ArgoCD's client-side-apply migration choked on `spec.ports[0].name: Required value`. Source aligned with live shape (`name: http, port: 80, targetPort: 5800/5801, protocol: TCP`). ceq-worker had no securityContext at all → Kyverno `restrict-capabilities` rejected every apply. Added pod-level `runAsNonRoot:true, runAsUser:1001, fsGroup:1001, seccompProfile`, container-level `privileged:false, allowPrivilegeEscalation:false, capabilities.drop:[ALL]`, explicit `ports: []`, and uppercase `REDIS_URL` (matches the migration Job pattern).
- **🟡 ceq OAuth client unregistered in Janua** — `app.ceq.lol` sign-in broken because Janua doesn't currently know the `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk` client. Either re-register that client OR rotate to a new client_id and update studio config. Operator action.
- ~~**🔴 ceq.lol returning 502 cluster-wide for ~7 h**~~ — Closed 2026-05-04 ~08:00 UTC via ceq#31. The `kustomization.yaml` used legacy `commonLabels:` which propagated into `Service.spec.selector` AND `Deployment.spec.selector.matchLabels`, but pod template labels (carrying `app.kubernetes.io/name=ceq-studio` / `part-of=ceq`) overrode commonLabels at the pod level. Net: selector required 4 labels, pods only had 3 with conflicting values → endpoints empty → cloudflared got connection-refused → 502 across `ceq.lol` / `app.ceq.lol` / `api.ceq.lol` for ~7 hours after the prior session's apply triggered the mismatch. **Live mitigation**: kubectl patched the Service selectors to drop the 3 commonLabels keys (HTTP 200 returned within seconds). **Permanent fix**: switched to `labels: [{ includeSelectors: false, pairs: ... }]` so metadata labels still tag every resource for dashboards but selectors stay untouched. Pattern to avoid in other repos: any kustomization that mixes `commonLabels` with Deployment templates that already declare their own `app.kubernetes.io/name` / `part-of` will eventually mismatch.

---

*"The terminal awaits. Let's quantize some chaos."* — ceq.lol
