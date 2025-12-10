# Vast.ai Setup Guide for CEQ Workers

Complete guide for setting up Vast.ai GPU infrastructure for CEQ ComfyUI workers.

## Overview

Vast.ai is a P2P GPU marketplace where you can rent GPUs by the second. CEQ uses Vast.ai for immediate GPU worker deployment while Furnace (Enclii internal) infrastructure is being developed.

**Key Benefits:**
- Pay-per-second billing (not hourly minimum)
- Wide GPU selection (RTX 3090 → H100)
- SSH + Docker deployment model
- Competitive pricing ($0.15-$2.00/hr typical)

---

## Step 1: Account Setup

### 1.1 Create Account
1. Go to [cloud.vast.ai](https://cloud.vast.ai)
2. Click "Sign Up" → Create account with email or OAuth
3. Verify email address

### 1.2 Add Payment Method
1. Navigate to **Billing** section
2. Click "Add Payment Method"
3. Options:
   - **Credit Card** (via Stripe) - recommended for automation
   - **Crypto** (via Crypto.com or Coinbase)
4. Add initial credits ($10-50 recommended for testing)

**Billing Details:**
- Credits are prepaid and consumed per-second
- **GPU costs**: Charged only while instance is running
- **Storage costs**: Charged continuously while instance exists
- **Bandwidth**: Charged per TB transferred
- Zero balance → instances stopped (not destroyed)

### 1.3 Get API Key
1. Go to [cloud.vast.ai/cli/](https://cloud.vast.ai/cli/)
2. Copy your API key (hexadecimal string)
3. **KEEP SECRET** - this authenticates all API operations

```bash
# Store securely
export VAST_API_KEY="your-hexadecimal-key-here"
```

---

## Step 2: SSH Key Configuration

### 2.1 Generate SSH Key (if needed)
```bash
# Generate new key pair
ssh-keygen -t ed25519 -C "ceq-worker" -f ~/.ssh/ceq_vastai

# View public key
cat ~/.ssh/ceq_vastai.pub
```

### 2.2 Add Key to Vast.ai
**Option A: Web Console**
1. Go to cloud.vast.ai → Account → SSH Keys
2. Paste your public key content
3. Save

**Option B: CLI**
```bash
vastai create ssh-key "$(cat ~/.ssh/ceq_vastai.pub)"
```

Keys are automatically added to all new instances.

---

## Step 3: CLI Installation

### 3.1 Install vastai CLI
```bash
# PyPI (stable)
pip install vastai

# Or latest from GitHub
wget https://raw.githubusercontent.com/vast-ai/vast-python/master/vast.py -O vast
chmod +x vast
```

### 3.2 Configure API Key
```bash
vastai set api-key $VAST_API_KEY
```

This stores credentials in `~/.vast_api_key`.

### 3.3 Verify Setup
```bash
# Should show your account info
vastai show user

# Should list available offers
vastai search offers --limit 5
```

---

## Step 4: Finding GPU Instances

### 4.1 Search Syntax

```bash
# Basic search - find verified machines with RTX 4090
vastai search offers 'verified=true gpu_name=RTX_4090'

# Price-filtered - max $0.50/hr, 16GB+ VRAM
vastai search offers 'dph_total<=0.50 gpu_ram>=16000 verified=true' --order dph_total

# High reliability for production
vastai search offers 'reliability>0.98 verified=true cuda_vers>=12.0' --order dph_total
```

### 4.2 Filter Operators

| Operator | Example | Meaning |
|----------|---------|---------|
| `=` | `gpu_name=RTX_4090` | Exact match |
| `>=` | `gpu_ram>=16000` | At least (VRAM in MB) |
| `<=` | `dph_total<=1.0` | At most ($/hr) |
| `>` | `reliability>0.95` | Greater than |

### 4.3 Key Filter Fields

| Field | Description | CEQ Recommendation |
|-------|-------------|-------------------|
| `verified` | Provider verified | `=true` (required) |
| `gpu_name` | GPU model | RTX 4090, A100, etc. |
| `gpu_ram` | VRAM in MB | `>=16000` (16GB min) |
| `num_gpus` | GPU count | `>=1` |
| `dph_total` | $/hour total | `<=1.0` for budget |
| `reliability` | Uptime score | `>0.95` for production |
| `cuda_vers` | CUDA version | `>=12.0` for modern |
| `disk_space` | Available GB | `>=50` |

### 4.4 Recommended Search for CEQ

```bash
# Best value for SDXL/video workloads
vastai search offers \
  'verified=true gpu_ram>=16000 reliability>0.95 cuda_vers>=12.0 dph_total<=1.0' \
  --order dph_total \
  --limit 10
```

---

## Step 5: Creating Instances

### 5.1 Using CEQ Deploy Script (Recommended)
```bash
cd /path/to/ceq/apps/workers

# Auto-select cheapest suitable GPU
./scripts/deploy-vast.sh

# Specific GPU with max price
./scripts/deploy-vast.sh "RTX 4090" 0.50
```

### 5.2 Manual CLI Creation

```bash
# Find offer ID from search
vastai search offers 'verified=true gpu_ram>=16000' --order dph_total

# Create instance (use offer ID from above)
vastai create instance 12345678 \
  --image ghcr.io/madfam/ceq-worker:latest \
  --disk 100 \
  --label "ceq-worker-1" \
  --onstart-cmd "docker pull ghcr.io/madfam/ceq-worker:latest && docker run -d --gpus all -p 8188:8188 ghcr.io/madfam/ceq-worker:latest"
```

### 5.3 API Creation

```bash
curl --request PUT \
  --url "https://console.vast.ai/api/v0/asks/${OFFER_ID}/" \
  --header "Authorization: Bearer ${VAST_API_KEY}" \
  --header "Content-Type: application/json" \
  --data '{
    "image": "ghcr.io/madfam/ceq-worker:latest",
    "disk": 100,
    "label": "ceq-worker",
    "env": {
      "REDIS_URL": "redis://your-redis:6379/14",
      "R2_ENDPOINT": "https://xxx.r2.cloudflarestorage.com"
    },
    "onstart": "docker run -d --gpus all -p 8188:8188 $IMAGE"
  }'
```

---

## Step 6: Instance Management

### 6.1 View Instances
```bash
# List all your instances
vastai show instances

# Show specific instance
vastai show instance 12345678
```

### 6.2 Connect to Instance
```bash
# SSH (port from `vastai show instance`)
ssh -p 12345 -i ~/.ssh/ceq_vastai root@<public-ip>

# Or using vastai convenience
vastai ssh-url 12345678
```

### 6.3 Lifecycle Control
```bash
# Stop (saves storage, stops GPU billing)
vastai stop instance 12345678

# Start (resume from stopped)
vastai start instance 12345678

# Destroy (deletes everything)
vastai destroy instance 12345678
```

---

## Step 7: ComfyUI Templates

### 7.1 Using Pre-built ComfyUI Template

Vast.ai offers pre-built ComfyUI templates:
1. Go to cloud.vast.ai → Templates
2. Search for "ComfyUI"
3. Select template with desired configuration
4. Create instance from template

### 7.2 CEQ Custom Template

For CEQ workers, use the custom image:
```bash
# Image with ComfyUI + custom nodes + queue consumer
ghcr.io/madfam/ceq-worker:latest

# Slim image (faster startup)
ghcr.io/madfam/ceq-worker:slim
```

---

## Step 8: Cost Optimization

### 8.1 Pricing Tiers

| GPU | Typical $/hr | VRAM | Best For |
|-----|--------------|------|----------|
| RTX 3090 | $0.20-0.40 | 24GB | SDXL, basic video |
| RTX 4090 | $0.40-0.80 | 24GB | Fast SDXL, Flux |
| A5000 | $0.30-0.50 | 24GB | Reliable production |
| A100 40GB | $1.00-2.00 | 40GB | Large models, training |
| H100 | $2.50-4.00 | 80GB | Maximum performance |

### 8.2 Cost Control Settings

```bash
# In CEQ orchestrator config
export CEQ_MAX_HOURLY_SPEND=5.0   # Max total $/hr
export VAST_MAX_PRICE=1.0          # Max per instance $/hr
export CEQ_IDLE_TIMEOUT=300        # Scale down after 5min idle
export CEQ_MIN_WORKERS=0           # Allow scale to zero
```

### 8.3 Instance Types

| Type | Billing | Best For |
|------|---------|----------|
| **On-demand** | Higher price, guaranteed | Production, critical jobs |
| **Interruptible** | Lower price, can be reclaimed | Batch processing, development |
| **Reserved** | Up to 50% discount | Predictable, continuous workloads |

---

## Step 9: Monitoring & Troubleshooting

### 9.1 Check Instance Logs
```bash
vastai logs 12345678 --tail 100
```

### 9.2 Health Check
```bash
# Check if ComfyUI is responding
curl http://<instance-ip>:8188/system_stats
```

### 9.3 Common Issues

| Issue | Solution |
|-------|----------|
| Instance won't start | Check credit balance, try different offer |
| SSH connection refused | Wait 2-3 min for startup, check port |
| ComfyUI not responding | Check logs, verify GPU allocation |
| High costs | Enable scale-to-zero, reduce idle timeout |

---

## Environment Variables Summary

```bash
# Required
export VAST_API_KEY="your-api-key"

# CEQ Worker Configuration
export REDIS_URL="redis://your-redis:6379/14"
export CEQ_WORKER_IMAGE="ghcr.io/madfam/ceq-worker:latest"

# Optional: R2 Storage
export R2_ENDPOINT="https://xxx.r2.cloudflarestorage.com"
export R2_ACCESS_KEY="your-access-key"
export R2_SECRET_KEY="your-secret-key"
export R2_BUCKET="ceq-assets"

# Cost Controls
export VAST_MAX_PRICE=1.0
export CEQ_MAX_WORKERS=5
export CEQ_MAX_HOURLY_SPEND=5.0
export CEQ_IDLE_TIMEOUT=300
```

---

## Quick Start Checklist

- [ ] Create Vast.ai account
- [ ] Add payment method & credits
- [ ] Get API key from cloud.vast.ai/cli
- [ ] Generate SSH key
- [ ] Add SSH key to Vast.ai account
- [ ] Install vastai CLI: `pip install vastai`
- [ ] Configure API key: `vastai set api-key $VAST_API_KEY`
- [ ] Test search: `vastai search offers --limit 5`
- [ ] Deploy worker: `./scripts/deploy-vast.sh`
- [ ] Verify connection: `ssh -p <port> root@<ip>`

---

## Next Steps

1. **Test Deployment**: Run `./scripts/deploy-vast.sh` to create first worker
2. **Connect Redis**: Ensure workers can reach your Redis instance
3. **Test Job Queue**: Submit test job through CEQ API
4. **Configure Orchestrator**: Run `python -m ceq_worker.orchestrator` for auto-scaling
5. **Monitor Costs**: Watch Vast.ai billing dashboard

---

## Resources

- **Vast.ai Documentation**: [docs.vast.ai](https://docs.vast.ai)
- **Vast.ai Console**: [cloud.vast.ai](https://cloud.vast.ai)
- **CLI Reference**: `vastai --help`
- **CEQ Worker Scripts**: `ceq/apps/workers/scripts/`
