#!/bin/bash
# List CEQ workers across providers
#
# Usage:
#   ./list-workers.sh [provider]
#
# Providers: vast, furnace, all (default)

set -e

PROVIDER="${1:-all}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}📊 CEQ Worker Status${NC}"
echo "================================================"

list_vast() {
    if [ -z "$VAST_API_KEY" ]; then
        echo -e "${YELLOW}⚠️ VAST_API_KEY not set, skipping Vast.ai${NC}"
        return
    fi

    echo -e "\n${GREEN}Vast.ai Workers:${NC}"

    if ! command -v vastai &> /dev/null; then
        pip install vastai -q
    fi

    vastai set api-key "$VAST_API_KEY" 2>/dev/null

    vastai show instances --label ceq-worker 2>/dev/null || echo "  No workers found"
}

list_furnace() {
    FURNACE_URL="${FURNACE_API_URL:-http://furnace-gateway:4210}"

    echo -e "\n${GREEN}Furnace Workers:${NC}"

    if ! curl -sf "$FURNACE_URL/health" >/dev/null 2>&1; then
        echo "  Furnace gateway not available"
        return
    fi

    curl -sf "$FURNACE_URL/instances?labels=app=ceq-worker" \
        -H "Authorization: Bearer ${FURNACE_API_KEY:-}" \
        | jq -r '.instances[] | "  \(.id) - \(.status) - \(.gpu_type)"' \
        2>/dev/null || echo "  No workers found"
}

case "$PROVIDER" in
    vast)
        list_vast
        ;;
    furnace)
        list_furnace
        ;;
    all|*)
        list_vast
        list_furnace
        ;;
esac

echo ""
