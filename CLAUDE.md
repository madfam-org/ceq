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

### Namespace
```bash
kubectl apply -f infrastructure/k8s/namespace.yaml
```

### Secrets
```bash
# Copy template and fill in values
cp infrastructure/k8s/secrets.prod.yaml infrastructure/k8s/secrets.local.yaml
vim infrastructure/k8s/secrets.local.yaml
kubectl apply -f infrastructure/k8s/secrets.local.yaml
```

### Deploy
```bash
kubectl apply -k infrastructure/k8s/
```

### Verify
```bash
kubectl get pods -n ceq
kubectl logs -n ceq deployment/ceq-api
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

---

*"The terminal awaits. Let's quantize some chaos."* — ceq.lol
