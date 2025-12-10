#!/bin/bash
# =============================================================================
# CEQ Production Deployment Script
# =============================================================================
#
# This script automates the deployment of CEQ to the Foundry infrastructure
# (Hetzner k3s + Cloudflare Tunnel).
#
# Prerequisites:
#   - kubectl configured with cluster access
#   - cloudflared CLI installed
#   - Docker logged into ghcr.io/madfam
#   - Cloudflare account with ceq.lol domain
#
# Usage:
#   ./scripts/deploy-ceq.sh [command]
#
# Commands:
#   check      - Verify prerequisites
#   tunnel     - Create/configure Cloudflare tunnel
#   build      - Build Docker images
#   push       - Push images to registry
#   deploy     - Deploy to Kubernetes
#   status     - Check deployment status
#   all        - Run full deployment pipeline
#
# =============================================================================

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NAMESPACE="ceq"
TUNNEL_NAME="ceq-prod"
REGISTRY="ghcr.io/madfam"
DOMAINS=("ceq.lol" "api.ceq.lol" "ws.ceq.lol")

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# =============================================================================
# Check Prerequisites
# =============================================================================
cmd_check() {
    log_info "Checking prerequisites..."
    local missing=0

    # Check kubectl
    if command -v kubectl &> /dev/null; then
        if kubectl cluster-info &> /dev/null; then
            log_success "kubectl: Connected to cluster"
        else
            log_error "kubectl: Not connected to cluster"
            missing=1
        fi
    else
        log_error "kubectl: Not installed"
        missing=1
    fi

    # Check cloudflared
    if command -v cloudflared &> /dev/null; then
        log_success "cloudflared: $(cloudflared --version | head -1)"
    else
        log_error "cloudflared: Not installed"
        log_info "  Install: brew install cloudflared"
        missing=1
    fi

    # Check Docker
    if command -v docker &> /dev/null; then
        if docker info &> /dev/null; then
            log_success "docker: Running"
        else
            log_error "docker: Not running"
            missing=1
        fi
    else
        log_error "docker: Not installed"
        missing=1
    fi

    # Check registry login
    if docker pull $REGISTRY/ceq-api:latest &> /dev/null 2>&1 || \
       grep -q "ghcr.io" ~/.docker/config.json 2>/dev/null; then
        log_success "registry: Authenticated to ghcr.io"
    else
        log_warn "registry: May need to login with 'docker login ghcr.io'"
    fi

    # Check project files
    if [[ -f "$PROJECT_ROOT/apps/api/Dockerfile" ]]; then
        log_success "api/Dockerfile: Found"
    else
        log_error "api/Dockerfile: Missing"
        missing=1
    fi

    if [[ -f "$PROJECT_ROOT/apps/studio/Dockerfile" ]]; then
        log_success "studio/Dockerfile: Found"
    else
        log_error "studio/Dockerfile: Missing"
        missing=1
    fi

    if [[ -f "$PROJECT_ROOT/infrastructure/k8s/kustomization.yaml" ]]; then
        log_success "k8s/kustomization.yaml: Found"
    else
        log_error "k8s/kustomization.yaml: Missing"
        missing=1
    fi

    echo ""
    if [[ $missing -eq 0 ]]; then
        log_success "All prerequisites met!"
        return 0
    else
        log_error "Missing prerequisites. Please install/configure and retry."
        return 1
    fi
}

# =============================================================================
# Create/Configure Cloudflare Tunnel
# =============================================================================
cmd_tunnel() {
    log_info "Configuring Cloudflare Tunnel..."

    # Check if tunnel exists
    if cloudflared tunnel list | grep -q "$TUNNEL_NAME"; then
        log_info "Tunnel '$TUNNEL_NAME' already exists"
        TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
    else
        log_info "Creating tunnel '$TUNNEL_NAME'..."
        cloudflared tunnel create "$TUNNEL_NAME"
        TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
        log_success "Created tunnel: $TUNNEL_ID"
    fi

    # Configure DNS routes
    log_info "Configuring DNS routes..."
    for domain in "${DOMAINS[@]}"; do
        log_info "  Adding route: $domain"
        cloudflared tunnel route dns "$TUNNEL_NAME" "$domain" 2>/dev/null || \
            log_warn "  Route may already exist for $domain"
    done

    # Export credentials for Kubernetes
    CREDS_FILE="$HOME/.cloudflared/$TUNNEL_ID.json"
    if [[ -f "$CREDS_FILE" ]]; then
        log_info "Tunnel credentials: $CREDS_FILE"

        # Create Kubernetes secret
        log_info "Creating Kubernetes secret..."
        kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

        kubectl create secret generic cloudflared-credentials \
            --namespace="$NAMESPACE" \
            --from-file=credentials.json="$CREDS_FILE" \
            --dry-run=client -o yaml | kubectl apply -f -

        log_success "Cloudflare tunnel configured!"
    else
        log_error "Credentials file not found: $CREDS_FILE"
        log_info "Run 'cloudflared tunnel login' first"
        return 1
    fi

    # Display summary
    echo ""
    log_info "Tunnel Summary:"
    echo "  Tunnel ID:   $TUNNEL_ID"
    echo "  Tunnel Name: $TUNNEL_NAME"
    echo "  Domains:     ${DOMAINS[*]}"
    echo "  Credentials: $CREDS_FILE"
}

# =============================================================================
# Build Docker Images
# =============================================================================
cmd_build() {
    log_info "Building Docker images..."

    # Build API
    log_info "Building ceq-api..."
    docker build \
        -t "$REGISTRY/ceq-api:latest" \
        -t "$REGISTRY/ceq-api:$(git rev-parse --short HEAD)" \
        "$PROJECT_ROOT/apps/api"
    log_success "Built ceq-api"

    # Build Studio
    log_info "Building ceq-studio..."
    docker build \
        --build-arg NEXT_PUBLIC_API_URL=https://api.ceq.lol \
        --build-arg NEXT_PUBLIC_WS_URL=wss://ws.ceq.lol \
        -t "$REGISTRY/ceq-studio:latest" \
        -t "$REGISTRY/ceq-studio:$(git rev-parse --short HEAD)" \
        "$PROJECT_ROOT/apps/studio"
    log_success "Built ceq-studio"

    # Build Worker (optional - needs GPU for testing)
    if [[ "${BUILD_WORKER:-false}" == "true" ]]; then
        log_info "Building ceq-worker..."
        docker build \
            -t "$REGISTRY/ceq-worker:latest" \
            -t "$REGISTRY/ceq-worker:$(git rev-parse --short HEAD)" \
            "$PROJECT_ROOT/apps/workers"
        log_success "Built ceq-worker"
    else
        log_warn "Skipping worker build (set BUILD_WORKER=true to include)"
    fi

    # List images
    echo ""
    log_info "Built images:"
    docker images | grep "ceq-" | head -10
}

# =============================================================================
# Push Images to Registry
# =============================================================================
cmd_push() {
    log_info "Pushing images to registry..."

    docker push "$REGISTRY/ceq-api:latest"
    docker push "$REGISTRY/ceq-api:$(git rev-parse --short HEAD)"
    log_success "Pushed ceq-api"

    docker push "$REGISTRY/ceq-studio:latest"
    docker push "$REGISTRY/ceq-studio:$(git rev-parse --short HEAD)"
    log_success "Pushed ceq-studio"

    if [[ "${BUILD_WORKER:-false}" == "true" ]]; then
        docker push "$REGISTRY/ceq-worker:latest"
        docker push "$REGISTRY/ceq-worker:$(git rev-parse --short HEAD)"
        log_success "Pushed ceq-worker"
    fi

    log_success "All images pushed to $REGISTRY"
}

# =============================================================================
# Deploy to Kubernetes
# =============================================================================
cmd_deploy() {
    log_info "Deploying to Kubernetes..."

    # Check if secrets exist
    if ! kubectl get secret ceq-secrets -n "$NAMESPACE" &> /dev/null; then
        log_warn "ceq-secrets not found. Creating from template..."
        log_error "Please edit infrastructure/k8s/secrets.yaml with real values first!"
        log_info "Then run: kubectl apply -f infrastructure/k8s/secrets.yaml"
        return 1
    fi

    # Apply kustomization
    log_info "Applying Kubernetes manifests..."
    kubectl apply -k "$PROJECT_ROOT/infrastructure/k8s/"

    # Wait for rollout
    log_info "Waiting for deployments..."
    kubectl rollout status deployment/ceq-api -n "$NAMESPACE" --timeout=120s
    kubectl rollout status deployment/ceq-studio -n "$NAMESPACE" --timeout=120s
    kubectl rollout status deployment/cloudflared -n "$NAMESPACE" --timeout=60s

    log_success "Deployment complete!"
    cmd_status
}

# =============================================================================
# Check Deployment Status
# =============================================================================
cmd_status() {
    log_info "Deployment Status:"
    echo ""

    # Pods
    echo "=== Pods ==="
    kubectl get pods -n "$NAMESPACE" -o wide

    echo ""
    echo "=== Services ==="
    kubectl get svc -n "$NAMESPACE"

    echo ""
    echo "=== Endpoints ==="
    for domain in "${DOMAINS[@]}"; do
        status=$(curl -s -o /dev/null -w "%{http_code}" "https://$domain" 2>/dev/null || echo "---")
        if [[ "$status" == "200" ]] || [[ "$status" == "301" ]] || [[ "$status" == "302" ]]; then
            echo -e "  ${GREEN}✓${NC} https://$domain ($status)"
        else
            echo -e "  ${RED}✗${NC} https://$domain ($status)"
        fi
    done

    echo ""
    echo "=== API Health ==="
    curl -s "https://api.ceq.lol/health" 2>/dev/null | jq . || echo "  Not reachable"
}

# =============================================================================
# Full Deployment Pipeline
# =============================================================================
cmd_all() {
    log_info "Running full deployment pipeline..."
    echo ""

    cmd_check || return 1
    echo ""

    cmd_tunnel
    echo ""

    cmd_build
    echo ""

    cmd_push
    echo ""

    cmd_deploy
}

# =============================================================================
# Main
# =============================================================================
main() {
    cd "$PROJECT_ROOT"

    case "${1:-help}" in
        check)   cmd_check ;;
        tunnel)  cmd_tunnel ;;
        build)   cmd_build ;;
        push)    cmd_push ;;
        deploy)  cmd_deploy ;;
        status)  cmd_status ;;
        all)     cmd_all ;;
        *)
            echo "CEQ Deployment Script"
            echo ""
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  check   - Verify prerequisites"
            echo "  tunnel  - Create/configure Cloudflare tunnel"
            echo "  build   - Build Docker images"
            echo "  push    - Push images to registry"
            echo "  deploy  - Deploy to Kubernetes"
            echo "  status  - Check deployment status"
            echo "  all     - Run full deployment pipeline"
            echo ""
            echo "Environment Variables:"
            echo "  BUILD_WORKER=true  - Include worker image in build"
            ;;
    esac
}

main "$@"
