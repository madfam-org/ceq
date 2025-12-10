# ceq — Creative Entropy Quantized

> *The Skunkworks Terminal for the Generative Avant-Garde*

**ceq** wraps the raw power of [ComfyUI](https://github.com/comfyanonymous/ComfyUI) with a streamlined, hacker-centric interface. Full node power when you need it, a clean UX when you don't.

**Domain:** [ceq.lol](https://ceq.lol)
**Status:** Pre-production (Infrastructure pending)
**Philosophy:** *Wrestling order from the chaos of latent space*

---

## What is CEQ?

CEQ is MADFAM's internal content generation platform. It enables:

- **Social Media Content**: Automated post generation at scale
- **Video Clones**: AI-generated spokesperson content
- **3D Renders**: Product visualization and creative assets
- **Brand Consistency**: MADFAM aesthetic across all outputs

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
├── ceq-studio (Next.js 14)     → https://ceq.lol       (port 5801)
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
JANUA_URL=https://api.janua.dev
```

#### Studio (`apps/studio/.env.local`)
```bash
NEXT_PUBLIC_API_URL=http://localhost:5800
NEXT_PUBLIC_WS_URL=ws://localhost:5800
NEXT_PUBLIC_JANUA_DOMAIN=auth.madfam.io
NEXT_PUBLIC_JANUA_CLIENT_ID=jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk
```

---

## Development Commands

| Command | Description |
|---------|-------------|
| `pnpm install` | Install all dependencies |
| `pnpm build` | Build all packages |
| `pnpm typecheck` | Run TypeScript checks |
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
| ceq.lol | Studio | Pending |
| api.ceq.lol | API | Pending |
| ws.ceq.lol | WebSocket | Pending |

See [docs/PRODUCTION_DEPLOYMENT.md](./docs/PRODUCTION_DEPLOYMENT.md) for detailed deployment guide.

### Deployment Status (2025-12-10)

| Component | Status |
|-----------|--------|
| Janua OAuth Client | Registered |
| Cloudflare R2 Bucket | Created |
| Cloudflare Tunnel Routes | Configured |
| K8s Secrets | Partial (DB/Redis pending) |
| Infrastructure | Pending (Terraform not run) |

---

## Authentication

CEQ uses [Janua](https://github.com/madfam-io/janua) for authentication:

- **OAuth Provider:** auth.madfam.io
- **Client ID:** `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk`
- **Redirect URIs:**
  - `https://ceq.lol/auth/callback` (production)
  - `http://localhost:5801/auth/callback` (development)

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/PRD.md](./docs/PRD.md) | Product requirements & manifesto |
| [docs/PRODUCTION_DEPLOYMENT.md](./docs/PRODUCTION_DEPLOYMENT.md) | Production deployment guide |
| [apps/api/README.md](./apps/api/README.md) | API documentation |
| [apps/workers/README.md](./apps/workers/README.md) | GPU worker documentation |
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

PROPRIETARY - MADFAM

---

*"The terminal awaits. Let's quantize some chaos."* — ceq.lol
