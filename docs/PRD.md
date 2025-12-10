# PRD: ceq — Creative Entropy Quantized

> **The Skunkworks Terminal for the Generative Avant-Garde**

---

> **Version**: 1.0.0  
> **Status**: Draft  
> **Domain**: ceq.lol  
> **Created**: 2025-12-10  
> **Philosophy**: *Wrestling order from the chaos of latent space*

---

## Manifesto

**ceq** is not an "atelier" for passive users waiting to be served. It is a **high-velocity, hacker-centric terminal** for the mad scientists of MADFAM who demand tools that feel like raw extensions of their neural pathways.

The name—**Creative Entropy Quantized**—is a technical nod to what we actually do: take the infinite chaos of latent space and collapse it into something meaningful. The `.lol` domain isn't irony—it's a declaration that we don't take ourselves too seriously while taking our craft *deadly* seriously.

ceq brands itself as a **fearless sandbox** where:
- The friction of nodes dissolves into pure flow
- Creators "seek" the signal in the noise
- Industrial power meets indie irreverence
- Every workflow is a spell, every output is alchemy

---

## Strategic Position

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                       │
│     ComfyUI (Power)                    Consumer AI (Ease)            │
│         ┌───┐                              ┌───┐                     │
│         │███│                              │   │                     │
│         │███│                              │   │                     │
│         │███│                              │   │                     │
│         └───┘                              └───┘                     │
│           │                                  │                       │
│           │         ┌───────────┐            │                       │
│           └────────►│    ceq    │◄───────────┘                       │
│                     │   .lol    │                                    │
│                     │           │                                    │
│                     └───────────┘                                    │
│                           │                                          │
│                           ▼                                          │
│                   "Hacker's ComfyUI"                                 │
│              - Full node power when needed                           │
│              - Streamlined UX for common flows                       │
│              - MADFAM ecosystem integration                          │
│              - Latent chaos → shipped content                        │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Problem Statement

### The ComfyUI Paradox

ComfyUI is **insanely powerful** but has friction:
- 🧩 Node soup requires expertise to navigate
- 📦 Model management is scattered and manual
- 🔄 Workflows are brittle and hard to share
- 🚀 No path from "cool experiment" to "shipped content"

### Consumer AI Limitations

Midjourney, DALL-E, etc. are easy but:
- 🎭 No control beyond prompts
- 🔒 Locked ecosystems
- 💸 Per-generation costs add up
- 🧬 No reproducibility or iteration

### MADFAM's Specific Needs

1. **Social Media Content**: Automated post generation at scale
2. **Video Clones**: AI-generated spokesperson content
3. **3D Renders**: Product visualization and creative assets
4. **Brand Consistency**: MADFAM aesthetic across all outputs

---

## Goals & Non-Goals

### Goals

1. **G1**: Wrap ComfyUI with a streamlined UX that preserves full power
2. **G2**: Create MADFAM-specific workflow templates (social, video, 3D)
3. **G3**: Integrate with Janua for auth and team collaboration
4. **G4**: Run on Enclii/Furnace for GPU compute
5. **G5**: Ship content directly to MADFAM channels

### Non-Goals

- ❌ Replacing ComfyUI (we wrap, extend, enhance)
- ❌ Building for external customers (internal tool initially)
- ❌ Mobile-first (desktop/web power users)
- ❌ Competing with Midjourney (different market)

---

## Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                           ceq.lol                                     │
├──────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   ┌─────────────────────────────────────────────────────────────┐    │
│   │                     ceq-studio (Next.js)                      │    │
│   │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │    │
│   │   │ Workflow │  │  Asset   │  │  Output  │  │  Queue   │    │    │
│   │   │  Editor  │  │ Browser  │  │  Gallery │  │ Monitor  │    │    │
│   │   └──────────┘  └──────────┘  └──────────┘  └──────────┘    │    │
│   └─────────────────────────────────────────────────────────────┘    │
│                                │                                       │
│   ┌─────────────────────────────▼──────────────────────────────────┐ │
│   │                     ceq-api (FastAPI)                           │ │
│   │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │ │
│   │   │ Workflow │  │  Queue   │  │  Assets  │  │ Publish  │      │ │
│   │   │ Manager  │  │ Handler  │  │ Service  │  │ Pipeline │      │ │
│   │   └──────────┘  └──────────┘  └──────────┘  └──────────┘      │ │
│   └─────────────────────────────────────────────────────────────────┘ │
│                                │                                       │
│   ┌────────────────────────────▼────────────────────────────────────┐│
│   │                    ceq-workers (Python)                          ││
│   │   ┌────────────┐  ┌────────────┐  ┌────────────┐                ││
│   │   │  ComfyUI   │  │  ComfyUI   │  │  ComfyUI   │  (GPU Pods)    ││
│   │   │  Worker 1  │  │  Worker 2  │  │  Worker N  │                ││
│   │   └────────────┘  └────────────┘  └────────────┘                ││
│   └──────────────────────────────────────────────────────────────────┘│
│                                                                        │
│   ┌──────────────────────────────────────────────────────────────────┐│
│   │                    Dependencies                                   ││
│   │   Furnace (GPU) │ Janua (Auth) │ R2 (Storage) │ Redis (Queue)   ││
│   └──────────────────────────────────────────────────────────────────┘│
│                                                                        │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Details

#### 1. ceq-studio (`apps/studio/`)

**Technology**: Next.js 14 + shadcn/ui + Zustand  
**Purpose**: The terminal UI for power users

**Core Views**:

| View | Purpose |
|------|---------|
| **Workflow Editor** | Visual node editor (simplified ComfyUI nodes) |
| **Templates** | Pre-built workflows for common tasks |
| **Asset Browser** | Models, LoRAs, VAEs, embeddings |
| **Queue Monitor** | Real-time job status and history |
| **Output Gallery** | Generated content with metadata |
| **Publish** | One-click to MADFAM channels |

**Key Design Principles**:
- **Dark Mode Only**: This is a skunkworks, not a daycare
- **Keyboard-First**: Power users live in shortcuts
- **Real-Time Feedback**: WebSocket everything
- **Zero Chrome**: Maximum viewport for creation

#### 2. ceq-api (`apps/api/`)

**Technology**: FastAPI + SQLAlchemy  
**Purpose**: Workflow orchestration and job management

**Responsibilities**:
- Workflow CRUD and versioning
- Job queue management (Redis)
- Asset indexing and search
- Output management and publishing
- Furnace integration for GPU compute

**Key Endpoints**:
```
# Workflows
POST   /v1/workflows              # Create workflow
GET    /v1/workflows              # List workflows
GET    /v1/workflows/{id}         # Get workflow
PUT    /v1/workflows/{id}         # Update workflow
DELETE /v1/workflows/{id}         # Delete workflow
POST   /v1/workflows/{id}/run     # Execute workflow

# Jobs
GET    /v1/jobs                   # List jobs
GET    /v1/jobs/{id}              # Get job status
DELETE /v1/jobs/{id}              # Cancel job
WS     /v1/jobs/{id}/stream       # Real-time updates

# Assets
GET    /v1/assets                 # List assets
POST   /v1/assets                 # Upload asset
GET    /v1/assets/{id}            # Get asset

# Templates
GET    /v1/templates              # List templates
GET    /v1/templates/{id}         # Get template
POST   /v1/templates/{id}/fork    # Fork template to workflow

# Outputs
GET    /v1/outputs                # List outputs
GET    /v1/outputs/{id}           # Get output
POST   /v1/outputs/{id}/publish   # Publish to channel
```

#### 3. ceq-workers (`apps/workers/`)

**Technology**: Python + comfy_runner  
**Purpose**: ComfyUI execution on GPU

**Architecture**:
```python
# Uses Furnace handler pattern
import furnace
from comfy_runner import ComfyRunner

runner = ComfyRunner(
    comfyui_path="/opt/comfyui",
    model_path="/opt/models"
)

def handler(event):
    """Execute a ComfyUI workflow"""
    workflow = event["input"]["workflow"]
    inputs = event["input"]["params"]
    
    # Execute workflow
    result = runner.execute(
        workflow_json=workflow,
        input_values=inputs
    )
    
    # Upload outputs to R2
    output_urls = upload_outputs(result.outputs)
    
    return {
        "outputs": output_urls,
        "metadata": result.metadata,
        "execution_time": result.time
    }

furnace.serverless.start({"handler": handler})
```

**Model Management**:
- Base models stored in R2, cached on GPU node
- LoRAs, VAEs, embeddings loaded on-demand
- Automatic model pruning (LRU cache)

---

## Workflow Templates

### Template Categories

#### 🎨 Social Media (`templates/social/`)

| Template | Use Case |
|----------|----------|
| `post-generator` | Static image posts |
| `carousel-builder` | Multi-image carousels |
| `story-creator` | Vertical format stories |
| `thumbnail-forge` | Video thumbnails |

#### 🎬 Video Clone (`templates/video/`)

| Template | Use Case |
|----------|----------|
| `talking-head` | Spokesperson generation |
| `lip-sync` | Audio-to-video sync |
| `expression-transfer` | Emotion mapping |
| `avatar-animate` | Still-to-video |

#### 🧊 3D Rendering (`templates/3d/`)

| Template | Use Case |
|----------|----------|
| `product-render` | E-commerce visualization |
| `scene-builder` | Environmental rendering |
| `texture-gen` | Material generation |
| `multiview-gen` | Multi-angle generation |

#### 🔧 Utility (`templates/utility/`)

| Template | Use Case |
|----------|----------|
| `upscale-enhance` | Resolution enhancement |
| `background-remove` | Subject isolation |
| `style-transfer` | Aesthetic conversion |
| `batch-process` | Bulk operations |

---

## User Experience

### The "Seek" Flow

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                      │
│  1. TEMPLATE SELECT          2. CONFIGURE              3. GENERATE  │
│  ┌──────────────────┐       ┌──────────────────┐       ┌──────────┐│
│  │  📱 Social Post  │  →    │  Prompt: ______  │  →    │   🔄     ││
│  │  🎬 Video Clone  │       │  Style: [Modern] │       │  Running ││
│  │  🧊 3D Render    │       │  Seed: [Random]  │       │          ││
│  │  🔧 Custom       │       │  [Advanced ▼]    │       │  ████░░  ││
│  └──────────────────┘       └──────────────────┘       └──────────┘│
│                                                                      │
│  4. REVIEW                   5. ITERATE                 6. SHIP     │
│  ┌──────────────────┐       ┌──────────────────┐       ┌──────────┐│
│  │   ┌──────────┐   │       │  [Tweak Prompt]  │       │ → Twitter││
│  │   │ 🖼️ Output│   │  →    │  [Adjust Params] │  →    │ → Insta  ││
│  │   └──────────┘   │       │  [Re-run ↻]      │       │ → Gallery││
│  │   ⭐ ⭐ ⭐ ⭐ ☆    │       │                  │       │          ││
│  └──────────────────┘       └──────────────────┘       └──────────┘│
│                                                                      │
└────────────────────────────────────────────────────────────────────┘
```

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `⌘ + Enter` | Run workflow |
| `⌘ + K` | Command palette |
| `⌘ + N` | New workflow |
| `⌘ + S` | Save workflow |
| `⌘ + Shift + P` | Publish output |
| `Tab` | Next input |
| `Escape` | Cancel / Close |
| `Space` | Preview fullscreen |

### Brand Voice in UI

```
Loading state:    "Quantizing entropy..."
Success:          "Signal acquired. 📡"
Error:            "Chaos won this round. Retry? [↻]"
Queue waiting:    "In the crucible..."
Processing:       "Transmuting latent space..."
Complete:         "Materialized. ✨"
```

---

## Database Schema

```sql
-- Workflows
CREATE TABLE ceq_workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,  -- From Janua
    
    name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- ComfyUI workflow JSON
    workflow_json JSONB NOT NULL,
    
    -- Input schema for UI
    input_schema JSONB DEFAULT '{}',
    
    -- Metadata
    template_id UUID REFERENCES ceq_templates(id),
    is_public BOOLEAN DEFAULT false,
    tags TEXT[],
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Templates (pre-built workflows)
CREATE TABLE ceq_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    category VARCHAR(50) NOT NULL,  -- 'social', 'video', '3d', 'utility'
    
    -- ComfyUI workflow
    workflow_json JSONB NOT NULL,
    input_schema JSONB NOT NULL,
    
    -- Display
    thumbnail_url TEXT,
    preview_urls TEXT[],
    
    -- Metadata
    tags TEXT[],
    model_requirements TEXT[],  -- Required models
    vram_requirement_gb INT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Jobs (execution history)
CREATE TABLE ceq_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES ceq_workflows(id),
    user_id UUID NOT NULL,
    
    -- Input/Output
    input_params JSONB NOT NULL,
    output_urls TEXT[],
    
    -- Status
    status VARCHAR(50) DEFAULT 'queued',
    error TEXT,
    
    -- Timing
    queued_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    
    -- Furnace job reference
    furnace_job_id UUID
);

-- Assets (models, LoRAs, etc.)
CREATE TABLE ceq_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    name VARCHAR(255) NOT NULL,
    asset_type VARCHAR(50) NOT NULL,  -- 'checkpoint', 'lora', 'vae', 'embedding'
    
    -- Storage
    storage_uri TEXT NOT NULL,
    size_bytes BIGINT,
    
    -- Metadata
    description TEXT,
    tags TEXT[],
    preview_url TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Outputs (generated content)
CREATE TABLE ceq_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES ceq_jobs(id),
    user_id UUID NOT NULL,
    
    -- Content
    output_type VARCHAR(50) NOT NULL,  -- 'image', 'video', 'model'
    storage_uri TEXT NOT NULL,
    thumbnail_uri TEXT,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    
    -- Publishing
    published_to JSONB DEFAULT '[]',  -- [{"channel": "twitter", "url": "..."}]
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Port Allocation

ceq uses the **5800-5899** port block per PORT_ALLOCATION.md:

| Port | Service | Purpose |
|------|---------|---------|
| 5800 | ceq-api | FastAPI workflow orchestration |
| 5801 | ceq-studio | Next.js frontend |
| 5802 | ceq-admin | Admin dashboard (internal) |
| 5810-5819 | ceq-workers | ComfyUI GPU workers |
| 5820 | ceq-ws | WebSocket real-time updates |
| 5890 | ceq-metrics | Prometheus endpoint |

---

## Integration Points

### Janua (Authentication)

```typescript
// ceq-studio/lib/auth.ts
import { JanuaProvider, useJanua } from '@janua/react-sdk';

export function AuthProvider({ children }) {
  return (
    <JanuaProvider 
      domain="auth.madfam.io"
      clientId="ceq-studio"
      redirectUri="https://ceq.lol/callback"
    >
      {children}
    </JanuaProvider>
  );
}
```

### Furnace (GPU Compute)

```python
# ceq-api/services/execution.py
from furnace import FurnaceClient

furnace = FurnaceClient(
    endpoint="http://furnace-gateway:4210",
    api_key=settings.FURNACE_API_KEY
)

async def execute_workflow(workflow: Workflow, params: dict):
    job = await furnace.endpoints.run(
        endpoint_id="ceq-worker",
        input={
            "workflow": workflow.workflow_json,
            "params": params
        }
    )
    return job
```

### R2 (Asset Storage)

```python
# ceq-api/services/storage.py
import boto3

r2 = boto3.client(
    's3',
    endpoint_url=settings.R2_ENDPOINT,
    aws_access_key_id=settings.R2_ACCESS_KEY,
    aws_secret_access_key=settings.R2_SECRET_KEY
)

async def upload_output(file_path: str, content_type: str):
    key = f"outputs/{uuid4()}"
    r2.upload_file(file_path, settings.R2_BUCKET, key)
    return f"{settings.R2_PUBLIC_URL}/{key}"
```

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1-2)

- [ ] Initialize ceq repository with monorepo structure
- [ ] Set up ceq-api (FastAPI skeleton)
- [ ] Set up ceq-studio (Next.js skeleton)
- [ ] Janua integration for authentication
- [ ] Basic workflow CRUD

### Phase 2: ComfyUI Integration (Week 2-4)

- [ ] Set up ComfyUI on GEX44
- [ ] Implement ceq-worker with comfy_runner
- [ ] Furnace endpoint for ceq-worker
- [ ] Job queue with Redis
- [ ] WebSocket for real-time updates

### Phase 3: Studio UI (Week 4-6)

- [ ] Workflow editor component
- [ ] Template browser
- [ ] Queue monitor
- [ ] Output gallery
- [ ] Dark mode styling

### Phase 4: Templates (Week 6-8)

- [ ] Social media templates
- [ ] Video clone templates
- [ ] 3D render templates
- [ ] Template input schema system

### Phase 5: Polish & Ship (Week 8-10)

- [ ] Publishing pipeline
- [ ] Performance optimization
- [ ] Documentation
- [ ] Domain setup (ceq.lol)
- [ ] Production deployment

---

## Tech Stack Summary

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, shadcn/ui, Zustand, TanStack Query |
| API | FastAPI, SQLAlchemy, Pydantic v2 |
| Workers | Python, comfy_runner, Furnace SDK |
| Queue | Redis |
| Database | PostgreSQL |
| Storage | Cloudflare R2 |
| GPU | Furnace (Enclii extension) |
| Auth | Janua |
| Hosting | Enclii |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Workflow execution < 30s | 80% of jobs |
| Cold start (ComfyUI) | < 15 seconds |
| Studio load time | < 2 seconds |
| Template completion rate | > 60% |
| User session duration | > 10 minutes |
| Content shipped to channels | 100+/week |

---

## Appendix

### A. ComfyUI Integration Research

**comfy_runner** (Selected Approach):
- Headless execution, no UI overhead
- Auto-download nodes/models
- Python API, easy to wrap

```python
from comfy_runner import ComfyRunner

runner = ComfyRunner()
result = runner.execute(workflow_json, inputs)
```

### B. Model Requirements

| Use Case | Models | VRAM |
|----------|--------|------|
| Social Media | SDXL, Flux Dev | 16GB |
| Video Clone | WAN 2.1, LivePortrait | 16GB |
| 3D Render | Hunyuan 3D, Stable Zero123 | 18GB |

GEX44 (20GB VRAM) covers all use cases.

### C. Domain Setup

1. Register `ceq.lol` 
2. Point DNS to Cloudflare
3. Configure tunnel to Enclii
4. SSL via Cloudflare

---

**Document Control**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2025-12-10 | MADFAM Engineering | Initial manifesto |

---

*"The terminal awaits. Let's quantize some chaos."* — ceq.lol
