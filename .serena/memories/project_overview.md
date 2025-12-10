# CEQ Project Overview

**Name**: ceq (Creative Entropy Quantized)
**Domain**: ceq.lol
**Port Block**: 5800-5899
**Repository**: https://github.com/madfam/ceq.git

## Purpose
ComfyUI wrapper for MADFAM's content production needs. Provides a streamlined, hacker-centric interface while maintaining full access to the underlying node system.

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
├── templates/        # Workflow templates (social, video, 3d)
├── docs/             # PRD and documentation
└── infrastructure/   # Kubernetes manifests
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, shadcn/ui, Zustand, Tailwind |
| API | FastAPI, SQLAlchemy, Pydantic v2, Python 3.11+ |
| Workers | Python, torch, ComfyUI integration |
| Queue | Redis |
| Database | PostgreSQL |
| Storage | Cloudflare R2 |
| Auth | Janua (@janua/react-sdk) |
| GPU | Furnace (Enclii extension) |

## Internal Dependencies
- **Janua** (auth.madfam.io): Authentication
- **Furnace**: GPU compute scheduling
- **Enclii**: Platform hosting

## Key Characteristics
- Dark mode only
- Keyboard-first UX
- Terminal aesthetic (monospace fonts, minimal chrome)
- GPU workloads via Furnace, never direct GPU access
