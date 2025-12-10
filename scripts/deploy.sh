#!/usr/bin/env bash
# =============================================================================
# CEQ Deployment Script
# =============================================================================
#
# Deploys CEQ to production at ceq.lol
#
# Prerequisites:
#   - kubectl configured for production cluster
#   - Secrets configured in infrastructure/k8s/secrets.prod.yaml
#   - Cloudflare tunnel routes configured
#
# Usage: ./scripts/deploy.sh [command]
# Commands: check, deploy, status, migrate, seed, logs
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
K8S_DIR="$ROOT_DIR/infrastructure/k8s"

log_info() { echo -e "${BLUE}ℹ ${NC}$1"; }
log_success() { echo -e "${GREEN}✓ ${NC}$1"; }
log_warn() { echo -e "${YELLOW}⚠ ${NC}$1"; }
log_error() { echo -e "${RED}✗ ${NC}$1"; }

# Check prerequisites
check_prereqs() {
    log_info "Checking prerequisites..."

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found. Please install kubectl."
        exit 1
    fi

    # Check cluster access
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster. Check your kubeconfig."
        exit 1
    fi

    log_success "kubectl connected to cluster"

    # Check namespace
    if ! kubectl get namespace ceq &> /dev/null; then
        log_warn "CEQ namespace does not exist. It will be created on deploy."
    else
        log_success "CEQ namespace exists"
    fi

    # Check secrets
    if ! kubectl get secret ceq-secrets -n ceq &> /dev/null 2>&1; then
        log_warn "CEQ secrets not found. Apply secrets.prod.yaml first:"
        echo "  kubectl apply -f $K8S_DIR/secrets.prod.yaml"
    else
        log_success "CEQ secrets configured"
    fi

    # Check cloudflared
    if kubectl get deployment cloudflared -n ceq &> /dev/null 2>&1; then
        log_success "Cloudflared tunnel deployed"
    else
        log_warn "Cloudflared not yet deployed"
    fi
}

# Deploy all resources
deploy() {
    log_info "Deploying CEQ to production..."

    # Apply all resources
    kubectl apply -k "$K8S_DIR/"

    log_info "Waiting for deployments..."

    # Wait for deployments
    kubectl rollout status deployment/ceq-api -n ceq --timeout=180s || {
        log_error "API deployment failed"
        kubectl logs deployment/ceq-api -n ceq --tail=50
        exit 1
    }

    kubectl rollout status deployment/ceq-studio -n ceq --timeout=180s || {
        log_error "Studio deployment failed"
        kubectl logs deployment/ceq-studio -n ceq --tail=50
        exit 1
    }

    kubectl rollout status deployment/cloudflared -n ceq --timeout=120s || {
        log_error "Cloudflared deployment failed"
        kubectl logs deployment/cloudflared -n ceq --tail=50
        exit 1
    }

    log_success "All deployments complete!"

    # Show status
    status
}

# Run database migrations
migrate() {
    log_info "Running database migrations..."

    # Delete old job if exists
    kubectl delete job ceq-db-migrate -n ceq --ignore-not-found=true

    # Apply migration job
    kubectl apply -f "$K8S_DIR/db-migrate-job.yaml"

    # Wait for completion
    kubectl wait --for=condition=complete job/ceq-db-migrate -n ceq --timeout=120s || {
        log_error "Migration failed"
        kubectl logs job/ceq-db-migrate -n ceq
        exit 1
    }

    log_success "Migrations complete!"
}

# Seed templates
seed() {
    log_info "Seeding templates..."

    # Delete old job if exists
    kubectl delete job ceq-seed-templates -n ceq --ignore-not-found=true

    # Apply seed job
    kubectl apply -f "$K8S_DIR/db-migrate-job.yaml"

    # Wait for completion
    kubectl wait --for=condition=complete job/ceq-seed-templates -n ceq --timeout=120s || {
        log_error "Seeding failed"
        kubectl logs job/ceq-seed-templates -n ceq
        exit 1
    }

    log_success "Templates seeded!"
}

# Show status
status() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 CEQ DEPLOYMENT STATUS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    echo "🔷 Pods:"
    kubectl get pods -n ceq -o wide
    echo ""

    echo "🔷 Services:"
    kubectl get svc -n ceq
    echo ""

    echo "🔷 Endpoints:"
    echo "  • Studio:    https://ceq.lol"
    echo "  • API:       https://api.ceq.lol"
    echo "  • WebSocket: wss://ws.ceq.lol"
    echo ""

    # Quick health check
    echo "🔷 Health Check:"
    API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://api.ceq.lol/health 2>/dev/null || echo "000")
    if [ "$API_STATUS" == "200" ]; then
        echo "  • API: ✅ Healthy"
    else
        echo "  • API: ⚠️  HTTP $API_STATUS"
    fi

    STUDIO_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://ceq.lol 2>/dev/null || echo "000")
    if [ "$STUDIO_STATUS" == "200" ] || [ "$STUDIO_STATUS" == "301" ] || [ "$STUDIO_STATUS" == "302" ]; then
        echo "  • Studio: ✅ Healthy"
    else
        echo "  • Studio: ⚠️  HTTP $STUDIO_STATUS"
    fi
}

# Show logs
logs() {
    local component="${1:-api}"

    case "$component" in
        api)
            kubectl logs deployment/ceq-api -n ceq -f
            ;;
        studio)
            kubectl logs deployment/ceq-studio -n ceq -f
            ;;
        tunnel|cloudflared)
            kubectl logs deployment/cloudflared -n ceq -f
            ;;
        *)
            log_error "Unknown component: $component"
            echo "Valid components: api, studio, tunnel"
            exit 1
            ;;
    esac
}

# Main
main() {
    case "${1:-help}" in
        check)
            check_prereqs
            ;;
        deploy)
            deploy
            ;;
        migrate)
            migrate
            ;;
        seed)
            seed
            ;;
        status)
            status
            ;;
        logs)
            logs "${2:-api}"
            ;;
        help|*)
            echo "CEQ Deployment Script"
            echo ""
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  check   - Check prerequisites"
            echo "  deploy  - Deploy all resources"
            echo "  migrate - Run database migrations"
            echo "  seed    - Seed template data"
            echo "  status  - Show deployment status"
            echo "  logs    - Show logs (api|studio|tunnel)"
            echo ""
            echo "Typical workflow:"
            echo "  1. Configure secrets: cp infrastructure/k8s/secrets.prod.yaml secrets.local.yaml && vim secrets.local.yaml"
            echo "  2. Apply secrets: kubectl apply -f secrets.local.yaml"
            echo "  3. Deploy: $0 deploy"
            echo "  4. Migrate: $0 migrate"
            echo "  5. Check: $0 status"
            ;;
    esac
}

main "$@"
