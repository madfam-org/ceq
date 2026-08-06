# ceq — Creative Entropy Quantized

> *The Skunkworks Terminal for the Generative Avant-Garde*

**ceq** wraps the raw power of [ComfyUI](https://github.com/comfyanonymous/ComfyUI) with a streamlined, hacker-centric interface. Full node power when you need it, a clean UX when you don't.

**Domain:** [ceq.lol](https://ceq.lol)
**Status:** Live public surfaces; not commercial GA. Public smoke is green, but authenticated smoke, ExternalSecret health, GPU golden-path proof, and paid-launch controls remain open.
**Philosophy:** *Wrestling order from the chaos of latent space*

---

## Current documentation truth

Start with [`docs/README.md`](./docs/README.md), then the latest audit wrap-up
and evidence:

- [`docs/CEQ_CODEBASE_AUDIT_WRAPUP_2026-06-02.md`](./docs/CEQ_CODEBASE_AUDIT_WRAPUP_2026-06-02.md)
- [`docs/DOCS_EVIDENCE_AUDIT_2026-06-02.md`](./docs/DOCS_EVIDENCE_AUDIT_2026-06-02.md)

Older roadmap, deployment, and handoff docs preserve historical context. When
they conflict, the latest evidence audit wins.

---

## What is CEQ?

CEQ is MADFAM's internal content generation platform. It enables:

- **Social Media Content**: Automated post generation at scale
- **Video Clones**: AI-generated spokesperson content
- **3D Renders**: Product visualization and creative assets
- **Brand Consistency**: MADFAM aesthetic across all outputs
- **Generic asset rendering (`/v1/render/*`)**: Deterministic, content-addressed cards / thumbnails for any MADFAM service that needs a stable URL — see [`@ceq/sdk`](./packages/sdk/README.md) and [API docs](./apps/api/README.md#render-generative-assets).

```
┌─────────────────────────────────────────────────────────────────────┐
│     ComfyUI (Power)                    Consumer AI (Ease)          │
│         ┌───┐                              ┌───┐                   │
│         │███│                              │   │                   │
│         └───┘                              └───┘                   │
│           │         ┌───────────┐            │                     │
│           └────────►│    ceq    │◄───────────┘                     │
│                     │   .lol    │                                  │
│                     └───────────┘                                  │
│                   "Hacker's ComfyUI"                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Architecture

```
ceq.lol
├── ceq-landing (Next.js 14)    → https://ceq.lol       (marketing + demo)
├── ceq-studio (Next.js 14)     → https://app.ceq.lol   (authenticated app)
├── ceq-api (FastAPI)           → https://api.ceq.lol   (port 5800)
├── ceq-workers (ComfyUI)       → GPU instances          (ports 5810-5819)
└── Dependencies
    ├── Janua (auth.madfam.io)  → Authentication
    ├── Redis                   → Job queue (DB 14)
    ├── PostgreSQL              → Metadata storage
    └── Cloudflare R2           → Asset & output storage
```

### Directory Structure

```
ceq/
├── apps/
│   ├── studio/       # Next.js frontend
│   ├── api/          # FastAPI orchestration
│   └── workers/      # ComfyUI GPU workers
├── packages/
│   ├── ui/           # Shared UI components
│   ├── workflow-types/
│   └── sdk/
├── templates/        # Pre-built ComfyUI workflows
│   ├── social/       # Social media content
│   ├── video/        # Video clone workflows
│   └── 3d/           # 3D rendering
├── infrastructure/
│   └── k8s/          # Kubernetes manifests
├── docs/
│   ├── PRD.md        # Product requirements
│   └── PRODUCTION_DEPLOYMENT.md
└── scripts/          # Deployment utilities
```

---

## Quick Start

### Prerequisites

- Node.js 20+
- Python 3.11+
- pnpm 8+
- Docker (for workers)

### Development Setup

```bash
# Clone and install
git clone https://github.com/madfam-io/ceq.git
cd ceq
pnpm install

# Start the Studio (frontend)
pnpm --filter @ceq/studio dev
# → http://localhost:5801

# Start the API (in another terminal)
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn ceq_api.main:app --port 5800 --reload
# → http://localhost:5800

# Workers require GPU - see apps/workers/README.md
```

### Environment Variables

#### API (`apps/api/.env`)
```bash
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/ceq
REDIS_URL=redis://:password@host:6379/14
R2_ENDPOINT=https://xxx.r2.cloudflarestorage.com
R2_ACCESS_KEY=your-access-key
R2_SECRET_KEY=your-secret-key
R2_BUCKET=ceq-assets
# Kubernetes secrets use R2_BUCKET_NAME; local config accepts either name.
# R2_BUCKET_NAME=ceq-assets
JANUA_URL=https://api.janua.dev
JOB_COMPLETION_CALLBACK_TOKEN=dev-shared-worker-callback-token
JOB_WEBHOOK_SECRET=dev-shared-user-webhook-secret
JOB_WEBHOOK_MAX_ATTEMPTS=3
```

#### Studio (`apps/studio/.env.local`)
```bash
NEXT_PUBLIC_API_URL=http://localhost:5800
NEXT_PUBLIC_WS_URL=ws://localhost:5800
NEXT_PUBLIC_JANUA_URL=https://auth.madfam.io
NEXT_PUBLIC_JANUA_CLIENT_ID=jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk
NEXT_PUBLIC_DHANAM_BILLING_URL=https://api.dhan.am
NEXT_PUBLIC_CEQ_CHECKOUT_ENABLED=false
```

#### Workers
```bash
REDIS_URL=redis://:password@host:6379/14
API_URL=http://localhost:5800
API_JOB_COMPLETION_TOKEN=dev-shared-worker-callback-token
API_JOB_COMPLETION_MAX_ATTEMPTS=3
API_JOB_COMPLETION_RETRY_BACKOFF_SECONDS=1
JOB_COMPLETION_DEAD_LETTER_KEY=ceq:jobs:completion:dead
R2_ENDPOINT=https://xxx.r2.cloudflarestorage.com
R2_ACCESS_KEY=your-access-key
R2_SECRET_KEY=your-secret-key
R2_BUCKET=ceq-assets
```

---

## Development Commands

| Command | Description |
|---------|-------------|
| `pnpm install` | Install all dependencies |
| `pnpm build` | Build all packages |
| `pnpm typecheck` | Run TypeScript checks |
| `pnpm --filter @ceq/studio test` | Studio unit tests (Vitest) |
| `pnpm --filter @ceq/studio test:e2e` | Studio auth E2E (Playwright + mocked Janua) |
| `bash scripts/studio-docker-smoke.sh <image>` | Verify Studio Docker entrypoint + HTTP |
| `pnpm --filter @ceq/studio dev` | Run studio locally |
| `pnpm --filter @ceq/studio build` | Build studio for production |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, shadcn/ui, Zustand, TanStack Query |
| API | FastAPI, SQLAlchemy, Pydantic v2 |
| Workers | Python, comfy_runner |
| Queue | Redis |
| Database | PostgreSQL |
| Storage | Cloudflare R2 |
| Auth | Janua (@janua/react-sdk) |
| GPU | Vast.ai (current) / Furnace (future) |
| Hosting | Enclii (k3s on Hetzner) |

---

## Port Allocation

Per MADFAM [PORT_ALLOCATION.md](https://github.com/madfam-io/solarpunk-foundry/blob/main/docs/PORT_ALLOCATION.md), CEQ uses **5800-5899**:

| Port | Service | Description |
|------|---------|-------------|
| 5800 | ceq-api | FastAPI orchestration |
| 5801 | ceq-studio | Next.js frontend |
| 5810-5819 | ceq-workers | ComfyUI GPU workers |
| 5820 | ceq-ws | WebSocket updates |
| 5890 | ceq-metrics | Prometheus endpoint |

---

## Production Deployment

CEQ is deployed to Enclii infrastructure via Cloudflare Tunnels:

| Domain | Service | Status |
|--------|---------|--------|
| ceq.lol | Landing + demo | Live (2 pods) |
| app.ceq.lol | Studio app | Live + auth-gated; Janua client registered |
| api.ceq.lol | API | Live (2 pods) |
| ws.ceq.lol | WebSocket | Configured |

See [docs/PRODUCTION_DEPLOYMENT.md](./docs/PRODUCTION_DEPLOYMENT.md) for detailed deployment guide.

### Deployment Status (2026-06-01)

| Component | Status |
|-----------|--------|
| Janua OAuth Client | Registered; authorize returns 302 and Studio token route accepts client credentials (`invalid_grant` for bogus code, not `invalid_client`) |
| Cloudflare R2 Bucket | Live (`ceq-assets`; render cache under `render/{template}/{hash}.{ext}`) |
| Cloudflare Tunnel Routes | Configured |
| `/v1/render/*` pipeline | Shipped — card renderer + R2 cache + `@ceq/sdk` |
| Studio auth gate | Deployed; public no-cookie app gate verified |
| Runtime secret state | K8s Secret exists and fallback GitHub sync is refreshed; ExternalSecret remains degraded until Vault `secret/ceq.JANUA_CLIENT_SECRET` is populated |
| Infrastructure | Live on Enclii k3s |

---

## Authentication

CEQ uses [Janua](https://github.com/madfam-io/janua) for authentication:

- **OAuth Provider:** auth.madfam.io
- **Client ID:** `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk`
- **Redirect URIs:**
  - `https://app.ceq.lol/auth/callback` (production Studio)
  - `http://localhost:5801/auth/callback` (development)

Public visitors should land on `https://ceq.lol` for the marketing/demo
experience. Authenticated product use starts at `https://app.ceq.lol`, which
redirects unauthenticated users to Janua. The Studio also sets httpOnly
session cookies after OAuth callback so app-host routes can be gated before the
React shell renders; browser bearer-token storage remains as a compatibility
bridge for the current direct API client.

As of the 2026-06-01 repo/prod audit, public smoke is green:
`ceq.lol` returns 200, `app.ceq.lol/` redirects no-cookie users to
`/login?returnTo=%2F`, `api.ceq.lol/health` returns `status: ok`, production
OpenAPI docs return 404, and unauthenticated `/v1/render/card` returns 401.
Full credentialed browser login still requires an operator with a real Janua
account to complete the acceptance checklist.

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/PRD.md](./docs/PRD.md) | Product requirements & manifesto |
| [docs/PRODUCTION_DEPLOYMENT.md](./docs/PRODUCTION_DEPLOYMENT.md) | Production deployment guide |
| [docs/CEQ_IDENTITY_AND_DEMO_WRAPUP.md](./docs/CEQ_IDENTITY_AND_DEMO_WRAPUP.md) | **Start here** — session wrap-up, doc index, operator gates |
| [docs/README.md](./docs/README.md) | Documentation map, precedence, and current truth layer |
| [docs/CEQ_CODEBASE_AUDIT_WRAPUP_2026-06-02.md](./docs/CEQ_CODEBASE_AUDIT_WRAPUP_2026-06-02.md) | Current audit wrap-up, live blockers, and ROI order |
| [docs/DOCS_EVIDENCE_AUDIT_2026-06-02.md](./docs/DOCS_EVIDENCE_AUDIT_2026-06-02.md) | Latest repo/prod evidence audit and remaining unverified claims |
| [docs/GA_DEMO_DEFINITION.md](./docs/GA_DEMO_DEFINITION.md) | Capped GA demo scope, readiness scorecard, acceptance |
| [docs/COMMERCIAL_GA_REMEDIATION_PLAN.md](./docs/COMMERCIAL_GA_REMEDIATION_PLAN.md) | Commercial GA gates, remediation tracks, pilot/launch plan |
| [docs/COMMERCIAL_LAUNCH_READINESS_PACK.md](./docs/COMMERCIAL_LAUNCH_READINESS_PACK.md) | Commercial launch evidence, support macros, alert/compliance readiness |
| [docs/JANUA_OPERATOR.md](./docs/JANUA_OPERATOR.md) | Janua OAuth registration & login unblock checklist |
| [docs/JANUA_AGENT_HANDOFF.md](./docs/JANUA_AGENT_HANDOFF.md) | Complete handoff for Janua-side agents |
| [docs/PLATFORM_AGENT_HANDOFFS.md](./docs/PLATFORM_AGENT_HANDOFFS.md) | Copy-paste prompts for Vault/K8s/acceptance agents |
| [docs/CEQ_STABILITY_ROADMAP.md](./docs/CEQ_STABILITY_ROADMAP.md) | Stabilization record and remaining roadmap |
| [apps/api/README.md](./apps/api/README.md) | API documentation (incl. `/v1/render/*` contract) |
| [apps/workers/README.md](./apps/workers/README.md) | GPU worker documentation |
| [packages/sdk/README.md](./packages/sdk/README.md) | `@ceq/sdk` — JS/TS client for the render API |
| [CLAUDE.md](./CLAUDE.md) | Agent/developer instructions |

---

## Related Projects

| Project | Description |
|---------|-------------|
| [Enclii](https://github.com/madfam-io/enclii) | Platform-as-a-Service hosting |
| [Janua](https://github.com/madfam-io/janua) | OAuth/OIDC authentication |
| [Solarpunk Foundry](https://github.com/madfam-io/solarpunk-foundry) | MADFAM ecosystem docs |

---

## License

This project is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0-only), per the MADFAM public-repo licensing policy (RFC 0024 P1.4).
See [LICENSE](./LICENSE) for the full text.

**Exception:** the [`@ceq/sdk`](./packages/sdk/) client package is
MIT-licensed so third parties can integrate it freely — see
[packages/sdk/LICENSE](./packages/sdk/LICENSE).

Copyright (c) 2026 Innovaciones MADFAM SAS de C.V.

---

*"The terminal awaits. Let's quantize some chaos."* — ceq.lol
