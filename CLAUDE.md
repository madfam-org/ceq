# CLAUDE.md - ceq Repository Instructions

> **ceq** — Creative Entropy Quantized  
> *The Skunkworks Terminal for the Generative Avant-Garde*

## Project Overview

**ceq** is a ComfyUI wrapper designed for MADFAM's content production needs. It wraps the raw power of ComfyUI with a streamlined, hacker-centric interface while maintaining full access to the underlying node system.

**Domain**: ceq.lol  
**Port Block**: 5800-5899  
**Philosophy**: Wrestling order from the chaos of latent space

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
├── docs/
│   └── PRD.md        # Product Requirements Document
└── infrastructure/
    └── k8s/          # Kubernetes manifests
```

## Tech Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| Frontend | Next.js 14, shadcn/ui, Zustand | Dark mode only |
| API | FastAPI, SQLAlchemy, Pydantic v2 | Python 3.11+ |
| Workers | Python, comfy_runner | Furnace SDK integration |
| Queue | Redis | Job queue, real-time updates |
| Database | PostgreSQL | Via Enclii shared infra |
| Storage | Cloudflare R2 | Assets and outputs |
| Auth | Janua | @janua/react-sdk |
| GPU | Furnace | Enclii extension |

## Dependencies

### Internal MADFAM Services

- **Janua** (auth.madfam.io): Authentication and user management
- **Furnace** (Enclii): GPU compute scheduling and billing
- **Enclii**: Platform hosting and deployment

### External Services

- **Cloudflare R2**: Asset and output storage
- **Redis**: Job queue and caching
- **PostgreSQL**: Metadata storage

## Development Commands

```bash
# Install dependencies
pnpm install

# Run studio locally (port 5801)
pnpm --filter @ceq/studio dev

# Run API locally (port 5800)
cd apps/api && ./venv/bin/uvicorn main:app --port 5800 --reload

# Run worker (requires GPU)
cd apps/workers && python main.py

# Build all
pnpm build

# Type check
pnpm typecheck
```

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
  "Signal acquired. 📡",
  "Materialized. ✨",
  "Entropy contained.",
];

// Error states
const ERROR_MESSAGES = [
  "Chaos won this round. Retry? [↻]",
  "Latent space turbulence detected.",
  "Signal lost in the noise.",
];
```

## Key Files

| File | Purpose |
|------|---------|
| `apps/api/main.py` | FastAPI entrypoint |
| `apps/studio/app/layout.tsx` | Root layout with providers |
| `apps/workers/handler.py` | Furnace handler for ComfyUI |
| `packages/ui/src/index.ts` | Shared UI components |
| `templates/*/workflow.json` | ComfyUI workflow definitions |

## Environment Variables

### API (apps/api/.env)
```bash
DATABASE_URL=postgres://...
REDIS_URL=redis://...
FURNACE_API_URL=http://furnace-gateway:4210
FURNACE_API_KEY=...
R2_ENDPOINT=https://...
R2_ACCESS_KEY=...
R2_SECRET_KEY=...
R2_BUCKET=ceq-assets
JANUA_API_URL=https://api.janua.dev
```

### Studio (apps/studio/.env)
```bash
NEXT_PUBLIC_API_URL=https://api.ceq.lol
NEXT_PUBLIC_JANUA_DOMAIN=auth.madfam.io
NEXT_PUBLIC_JANUA_CLIENT_ID=ceq-studio
```

## Important Notes

1. **ComfyUI Integration**: We use `comfy_runner` for headless execution, not the ComfyUI web UI
2. **GPU Scheduling**: All GPU workloads go through Furnace, never direct GPU access
3. **Asset Storage**: All models, outputs, and assets are stored in R2, cached on GPU nodes
4. **Real-time Updates**: Job progress via WebSocket on port 5820

## Related Documentation

- [PRD.md](./docs/PRD.md) - Full product requirements
- [Enclii PRD_FURNACE.md](../enclii/docs/architecture/PRD_FURNACE.md) - GPU infrastructure
- [PORT_ALLOCATION.md](../solarpunk-foundry/docs/PORT_ALLOCATION.md) - Port registry

---

*"The terminal awaits. Let's quantize some chaos."* — ceq.lol
