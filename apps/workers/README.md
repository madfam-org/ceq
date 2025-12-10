# CEQ Workers

GPU workers for ComfyUI workflow execution. Supports Vast.ai (current) and Furnace/Enclii (future).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  CEQ API (port 5800)                                            │
│  └── Enqueues jobs to Redis                                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ Redis DB 14
┌─────────────────────────────────────────────────────────────────┐
│  Orchestrator                                                    │
│  └── Manages worker instances on Vast.ai / Furnace              │
│  └── Auto-scales based on queue depth                           │
│  └── Health monitoring and cost control                         │
└─────────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│  Worker 1         │ │  Worker 2         │ │  Worker N         │
│  (RTX 4090)       │ │  (A100)           │ │  (RTX 3090)       │
│  └── ComfyUI      │ │  └── ComfyUI      │ │  └── ComfyUI      │
│  └── Queue Poll   │ │  └── Queue Poll   │ │  └── Queue Poll   │
└───────────────────┘ └───────────────────┘ └───────────────────┘
```

## Quick Start

### 1. Set Environment Variables

```bash
# Required for Vast.ai
export VAST_API_KEY="your-api-key"

# Required for job queue
export REDIS_URL="redis://localhost:6379/14"

# Optional: R2 storage for outputs
export R2_ENDPOINT="https://xxx.r2.cloudflarestorage.com"
export R2_ACCESS_KEY="your-access-key"
export R2_SECRET_KEY="your-secret-key"
export R2_BUCKET="ceq-assets"
```

### 2. Deploy a Worker to Vast.ai

```bash
# Auto-select cheapest GPU with ≥16GB VRAM
./scripts/deploy-vast.sh

# Specific GPU type with max price
./scripts/deploy-vast.sh "RTX 4090" 0.50
```

### 3. Run the Orchestrator (Auto-Scaling)

```bash
# Install and run
pip install -e .
python -m ceq_worker.orchestrator
```

## Components

| Component | Description |
|-----------|-------------|
| `handler.py` | Furnace/RunPod-compatible job handler |
| `queue.py` | Redis BRPOPLPUSH consumer |
| `comfyui.py` | Headless ComfyUI executor |
| `orchestrator.py` | Auto-scaling worker manager |
| `providers/` | GPU provider abstraction (Vast.ai, Furnace) |
| `storage.py` | R2/S3 output storage |

## GPU Provider Abstraction

The worker supports multiple GPU providers via a common interface:

```python
from ceq_worker.providers import get_provider

# Current: Vast.ai
provider = get_provider("vast")

# Future: Furnace (Enclii internal)
provider = get_provider("furnace")

# Create instance
instance = await provider.create_instance(spec)
```

### Vast.ai (Current)
- P2P GPU marketplace
- Wide GPU availability
- SSH + Docker deployment
- Pay-per-hour pricing

### Furnace (Future)
- Enclii internal infrastructure
- Waybill billing integration
- KEDA scale-to-zero
- Hetzner GEX44 GPU nodes

## Docker Images

### Full Image (~15GB)
Includes custom nodes for video, upscaling, ControlNet:
```bash
docker build -t ceq-worker:latest .
```

### Slim Image (~8GB)
Core SDXL/Flux support only:
```bash
docker build -f Dockerfile.slim -t ceq-worker:slim .
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/14` | Redis connection (DB 14) |
| `GPU_PROVIDER` | `vast` | Provider: vast, furnace |
| `VAST_API_KEY` | | Vast.ai API key |
| `VAST_MAX_PRICE` | `1.0` | Max $/hour per instance |
| `CEQ_MIN_WORKERS` | `0` | Minimum worker count |
| `CEQ_MAX_WORKERS` | `5` | Maximum worker count |
| `CEQ_IDLE_TIMEOUT` | `300` | Seconds before idle scale-down |
| `CEQ_MAX_HOURLY_SPEND` | `5.0` | Max $/hour total spend |

## Scripts

| Script | Description |
|--------|-------------|
| `deploy-vast.sh` | Deploy worker to Vast.ai |
| `list-workers.sh` | List all CEQ workers |
| `destroy-workers.sh` | Destroy all workers on provider |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Type checking
mypy src/

# Linting
ruff check src/

# Run tests
pytest
```

## License

PROPRIETARY - MADFAM
