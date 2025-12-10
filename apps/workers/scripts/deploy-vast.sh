#!/bin/bash
# CEQ Worker Deployment Script for Vast.ai
#
# This script deploys a CEQ worker instance to Vast.ai.
# It finds the cheapest available GPU and creates an instance.
#
# Prerequisites:
# - VAST_API_KEY environment variable
# - Docker image pushed to registry
# - SSH key configured
#
# Usage:
#   ./deploy-vast.sh [gpu_type] [max_price]
#
# Examples:
#   ./deploy-vast.sh                    # Auto-select cheapest GPU
#   ./deploy-vast.sh "RTX 4090" 0.50    # Specific GPU with max price

set -e

# Configuration
GPU_TYPE="${1:-}"
MAX_PRICE="${2:-1.0}"
WORKER_IMAGE="${CEQ_WORKER_IMAGE:-ghcr.io/madfam/ceq-worker:latest}"
DISK_GB="${CEQ_DISK_GB:-100}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔥 CEQ Worker Deployment - Vast.ai${NC}"
echo "================================================"

# Check API key
if [ -z "$VAST_API_KEY" ]; then
    echo -e "${RED}❌ VAST_API_KEY not set${NC}"
    echo "Set it with: export VAST_API_KEY=your_api_key"
    exit 1
fi

# Validate vastai CLI
if ! command -v vastai &> /dev/null; then
    echo -e "${YELLOW}Installing vastai CLI...${NC}"
    pip install vastai
fi

# Set API key
vastai set api-key "$VAST_API_KEY"

# Build search query
echo -e "\n${BLUE}🔍 Searching for GPU instances...${NC}"

QUERY="rentable=true verified=true"
QUERY="$QUERY dph_total<=$MAX_PRICE"
QUERY="$QUERY disk_space>=$DISK_GB"
QUERY="$QUERY cuda_vers>=12.0"

if [ -n "$GPU_TYPE" ]; then
    QUERY="$QUERY gpu_name=$GPU_TYPE"
else
    # Default: at least 16GB VRAM for SDXL/video workloads
    QUERY="$QUERY gpu_ram>=16000"
fi

# Search for offers
echo "Query: $QUERY"
OFFERS=$(vastai search offers "$QUERY" --order dph_total --limit 5)

if [ -z "$OFFERS" ]; then
    echo -e "${RED}❌ No matching GPU offers found${NC}"
    exit 1
fi

echo -e "\n${GREEN}Available offers:${NC}"
echo "$OFFERS" | head -20

# Get best offer ID
OFFER_ID=$(echo "$OFFERS" | awk 'NR==2 {print $1}')

if [ -z "$OFFER_ID" ]; then
    echo -e "${RED}❌ Could not parse offer ID${NC}"
    exit 1
fi

echo -e "\n${BLUE}🚀 Creating instance from offer: $OFFER_ID${NC}"

# Build environment variables
ENV_VARS=""
if [ -n "$REDIS_URL" ]; then
    ENV_VARS="$ENV_VARS -e REDIS_URL=$REDIS_URL"
fi
if [ -n "$R2_ENDPOINT" ]; then
    ENV_VARS="$ENV_VARS -e R2_ENDPOINT=$R2_ENDPOINT"
    ENV_VARS="$ENV_VARS -e R2_ACCESS_KEY=$R2_ACCESS_KEY"
    ENV_VARS="$ENV_VARS -e R2_SECRET_KEY=$R2_SECRET_KEY"
    ENV_VARS="$ENV_VARS -e R2_BUCKET=$R2_BUCKET"
fi

# Create startup script
ONSTART=$(cat <<'SCRIPT'
#!/bin/bash
set -e

echo "🔧 Setting up CEQ worker..."

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
fi

# Pull and run worker
docker pull $IMAGE
docker run -d \
    --gpus all \
    --name ceq-worker \
    --restart unless-stopped \
    -p 8188:8188 \
    -v /opt/models:/opt/models \
    -v /opt/outputs:/opt/outputs \
    $ENV_VARS \
    $IMAGE

echo "✅ CEQ worker started"
SCRIPT
)

# Create instance
RESULT=$(vastai create instance "$OFFER_ID" \
    --image "$WORKER_IMAGE" \
    --disk "$DISK_GB" \
    --label "ceq-worker" \
    --onstart-cmd "bash -c '$ONSTART'" \
    2>&1)

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to create instance:${NC}"
    echo "$RESULT"
    exit 1
fi

INSTANCE_ID=$(echo "$RESULT" | grep -oP 'new_contract:\s*\K\d+' || echo "")

if [ -z "$INSTANCE_ID" ]; then
    echo -e "${YELLOW}Instance creation initiated:${NC}"
    echo "$RESULT"
else
    echo -e "${GREEN}✅ Instance created: $INSTANCE_ID${NC}"
fi

# Wait for instance to be ready
echo -e "\n${BLUE}⏳ Waiting for instance to start...${NC}"

for i in {1..60}; do
    STATUS=$(vastai show instance "$INSTANCE_ID" 2>/dev/null | grep -oP 'actual_status:\s*\K\w+' || echo "pending")

    if [ "$STATUS" = "running" ]; then
        echo -e "${GREEN}✅ Instance is running!${NC}"

        # Get connection info
        INFO=$(vastai show instance "$INSTANCE_ID")
        IP=$(echo "$INFO" | grep -oP 'public_ipaddr:\s*\K[\d.]+' || echo "")
        SSH_PORT=$(echo "$INFO" | grep -oP 'ssh_port:\s*\K\d+' || echo "22")

        echo -e "\n${GREEN}Connection Info:${NC}"
        echo "  Instance ID: $INSTANCE_ID"
        echo "  IP Address:  $IP"
        echo "  SSH Port:    $SSH_PORT"
        echo ""
        echo "Connect with: ssh -p $SSH_PORT root@$IP"
        echo "ComfyUI at:   http://$IP:8188"
        exit 0
    fi

    echo "  Status: $STATUS (attempt $i/60)"
    sleep 10
done

echo -e "${YELLOW}⚠️ Instance may still be starting. Check with:${NC}"
echo "  vastai show instance $INSTANCE_ID"
