# CEQ Workers

GPU workers for ComfyUI workflow execution. Supports Vast.ai (current) and Furnace/Enclii (future).

## Overview

CEQ Workers execute ComfyUI workflows on GPU instances:
- Poll jobs from Redis queue (DB 14)
- Execute workflows via `comfy_runner`
- Upload outputs to Cloudflare R2
- Report status back to CEQ API

**Ports:** 5810-5819
**GPU Providers:** Vast.ai (current), Furnace (future)

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
export R2_ENDPOINT="https://12f1353f7819865c56161ce00297668e.r2.cloudflarestorage.com"
export R2_ACCESS_KEY="51844af3c4cbda516895116372ec3b38"
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

See [docs/VAST_AI_SETUP.md](../../docs/VAST_AI_SETUP.md) for setup guide.

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
| `R2_ENDPOINT` | | Cloudflare R2 endpoint |
| `R2_ACCESS_KEY` | | R2 access key ID |
| `R2_SECRET_KEY` | | R2 secret access key |
| `R2_BUCKET` | `ceq-assets` | R2 bucket name |

## Model Requirements

| Use Case | Models | VRAM Required |
|----------|--------|---------------|
| Social Media | SDXL, Flux Dev | 16GB |
| Video Clone | WAN 2.1, LivePortrait | 16GB |
| 3D Render | Hunyuan 3D, Stable Zero123 | 18GB |

Models are stored in R2 and cached on GPU nodes.

## Scripts

| Script | Description |
|--------|-------------|
| `deploy-vast.sh` | Deploy worker to Vast.ai |
| `list-workers.sh` | List all CEQ workers |
| `destroy-workers.sh` | Destroy all workers on provider |

## Job Handler

The worker uses a Furnace-compatible handler pattern:

```python
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

## Auto-Scaling Behavior

The orchestrator manages worker instances based on:

1. **Queue Depth**: Spawn workers when jobs are waiting
2. **Cost Limits**: Respect `CEQ_MAX_HOURLY_SPEND`
3. **Idle Timeout**: Destroy idle workers after `CEQ_IDLE_TIMEOUT`
4. **Min/Max Workers**: Stay within configured bounds

```python
# Scaling logic (simplified)
if queue_depth > 0 and workers < max_workers:
    spawn_worker()
elif idle_time > timeout and workers > min_workers:
    destroy_worker()
```

## Troubleshooting

### Worker not picking up jobs

```bash
# Check Redis connection
redis-cli -u $REDIS_URL LLEN ceq:jobs:pending

# Check worker logs
docker logs ceq-worker
```

### ComfyUI execution failing

```bash
# Check model availability
ls /opt/models/checkpoints/

# Check ComfyUI logs
cat /opt/comfyui/output/comfyui.log
```

### Vast.ai instance not starting

```bash
# Check API key
vastai show instances

# Check available GPUs
vastai search offers "gpu_name=RTX 4090 rentable=True"
```

## Port Allocation

Per [PORT_ALLOCATION.md](https://github.com/madfam-io/solarpunk-foundry/blob/main/docs/PORT_ALLOCATION.md):

| Service | Port |
|---------|------|
| Worker 1 | 5810 |
| Worker 2 | 5811 |
| ... | ... |
| Worker 10 | 5819 |

## License

PROPRIETARY - MADFAM
