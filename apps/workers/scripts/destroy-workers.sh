#!/bin/bash
# Destroy all CEQ workers on a provider
#
# Usage:
#   ./destroy-workers.sh [provider]
#
# Providers: vast, furnace
# WARNING: This destroys ALL ceq-worker instances!

set -e

PROVIDER="${1:-vast}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${RED}⚠️  WARNING: This will destroy ALL CEQ workers on $PROVIDER${NC}"
echo ""
read -p "Are you sure? (y/N): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

destroy_vast() {
    if [ -z "$VAST_API_KEY" ]; then
        echo -e "${RED}❌ VAST_API_KEY not set${NC}"
        exit 1
    fi

    if ! command -v vastai &> /dev/null; then
        pip install vastai -q
    fi

    vastai set api-key "$VAST_API_KEY"

    echo -e "${YELLOW}Finding Vast.ai workers...${NC}"

    # Get all instance IDs with ceq-worker label
    INSTANCES=$(vastai show instances --label ceq-worker --raw 2>/dev/null | jq -r '.[].id' 2>/dev/null || echo "")

    if [ -z "$INSTANCES" ]; then
        echo "No workers found."
        exit 0
    fi

    echo "Found workers: $INSTANCES"

    for ID in $INSTANCES; do
        echo -e "  Destroying instance $ID..."
        vastai destroy instance "$ID" || echo "  Failed to destroy $ID"
    done

    echo -e "${GREEN}✅ All workers destroyed${NC}"
}

destroy_furnace() {
    FURNACE_URL="${FURNACE_API_URL:-http://furnace-gateway:4210}"

    echo -e "${YELLOW}Finding Furnace workers...${NC}"

    INSTANCES=$(curl -sf "$FURNACE_URL/instances?labels=app=ceq-worker" \
        -H "Authorization: Bearer ${FURNACE_API_KEY:-}" \
        | jq -r '.instances[].id' 2>/dev/null || echo "")

    if [ -z "$INSTANCES" ]; then
        echo "No workers found."
        exit 0
    fi

    for ID in $INSTANCES; do
        echo "  Destroying instance $ID..."
        curl -sf -X DELETE "$FURNACE_URL/instances/$ID" \
            -H "Authorization: Bearer ${FURNACE_API_KEY:-}" \
            || echo "  Failed to destroy $ID"
    done

    echo -e "${GREEN}✅ All workers destroyed${NC}"
}

case "$PROVIDER" in
    vast)
        destroy_vast
        ;;
    furnace)
        destroy_furnace
        ;;
    *)
        echo "Unknown provider: $PROVIDER"
        echo "Usage: ./destroy-workers.sh [vast|furnace]"
        exit 1
        ;;
esac
