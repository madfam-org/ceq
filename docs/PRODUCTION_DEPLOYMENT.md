# CEQ Production Deployment Guide

> Deploy CEQ to production at ceq.lol via Enclii infrastructure

## Prerequisites

- Access to Cloudflare Zero Trust dashboard
- Access to Janua admin at https://auth.madfam.io/admin
- Access to Ubicloud console for PostgreSQL
- kubectl configured for k3s cluster
- GitHub repo write access for secrets
- Terraform installed (`brew install terraform`)

## Deployment Status (2025-12-10)

| Step | Status | Notes |
|------|--------|-------|
| Janua OAuth Client | Done | `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk` |
| Cloudflare Tunnel Routes | Done | ceq.lol, api.ceq.lol, ws.ceq.lol |
| R2 Bucket + Token | Done | `ceq-assets` with Object Read & Write |
| secrets.prod.yaml | Partial | R2 + OAuth done, DB/Redis pending |
| Enclii Infrastructure | Pending | Terraform not initialized |
| Ubicloud Database | Pending | Create ceq_production database |
| Redis Password | Pending | Get from terraform output |
| GitHub Actions Secret | Pending | KUBECONFIG_BASE64 |
| Deploy + Verify | Pending | Push to main branch |

## Blocking Issue

**The Enclii production k3s cluster doesn't exist yet.** Before CEQ can be deployed, you must first deploy the Enclii infrastructure:

```bash
cd /path/to/enclii
./scripts/deploy-production.sh check    # Validate config
./scripts/deploy-production.sh init     # Initialize Terraform
./scripts/deploy-production.sh apply    # Create infrastructure
./scripts/deploy-production.sh kubeconfig    # Get cluster access
./scripts/deploy-production.sh post-deploy   # Setup tunnel & namespaces
```

---

## Deployment Checklist

### 1. Deploy Enclii Infrastructure First

```bash
cd /path/to/enclii

# Create terraform.tfvars with Hetzner credentials
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
vim infra/terraform/terraform.tfvars

# Deploy infrastructure
./scripts/deploy-production.sh init
./scripts/deploy-production.sh apply
./scripts/deploy-production.sh kubeconfig
./scripts/deploy-production.sh post-deploy
```

### 2. Create Ubicloud PostgreSQL Database

```bash
# In Ubicloud Console:
# 1. Create new PostgreSQL instance (or add database to existing)
# 2. Create database: ceq_production
# 3. Create user: ceq with appropriate password
# 4. Note the connection details
```

### 3. Register OAuth Client in Janua (Done)

**Completed 2025-12-10.** Client registered with:

| Field | Value |
|-------|-------|
| **Name** | CEQ Studio |
| **Client ID** | `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk` |
| **Client Secret** | Stored in `secrets.prod.yaml` |
| **Grant Types** | `authorization_code`, `refresh_token` |
| **Redirect URIs** | `https://ceq.lol/auth/callback`, `http://localhost:5801/auth/callback` |
| **Scopes** | `openid`, `profile`, `email` |

### 4. Create Cloudflare R2 Bucket (Done)

**Completed 2025-12-10.** Resources created:

| Resource | Value |
|----------|-------|
| **Bucket** | `ceq-assets` (Western North America) |
| **Token** | `CEQ R2 Token` (Object Read & Write) |
| **Access Key** | Stored in `secrets.prod.yaml` |
| **Secret Key** | Stored in `secrets.prod.yaml` |
| **Endpoint** | `https://12f1353f7819865c56161ce00297668e.r2.cloudflarestorage.com` |

### 5. Configure Tunnel Routes (Done)

**Completed 2025-12-10.** Tunnel: `ceq-prod` (ID: `0de376f0-dd76-40ab-af58-1a5d63eb9b11`)

| Public Hostname | Service | Port |
|-----------------|---------|------|
| `ceq.lol` | `http://ceq-studio.ceq.svc.cluster.local` | 5801 |
| `api.ceq.lol` | `http://ceq-api.ceq.svc.cluster.local` | 5800 |
| `ws.ceq.lol` | `http://ceq-api.ceq.svc.cluster.local` | 5800 |

WebSocket support enabled for `ws.ceq.lol`.

### 6. Configure Production Secrets

```bash
# Copy the template
cp infrastructure/k8s/secrets.prod.yaml infrastructure/k8s/secrets.local.yaml

# Edit with real values
vim infrastructure/k8s/secrets.local.yaml

# Apply to cluster
kubectl apply -f infrastructure/k8s/secrets.local.yaml
```

Required values:
- `database-url`: Ubicloud PostgreSQL connection string
- `redis-url`: Redis Sentinel URL (DB 14)
- `r2-*`: Cloudflare R2 credentials (already filled)
- `janua-client-secret`: From Janua admin (already filled)

### 7. Create CEQ Namespace

```bash
kubectl apply -f infrastructure/k8s/namespace.yaml
```

### 8. Run Database Migrations

```bash
# Get a shell in the API pod (or run locally with prod DATABASE_URL)
cd apps/api
DATABASE_URL="postgresql+asyncpg://ceq:PASSWORD@HOST:5432/ceq_production" \
  .venv/bin/alembic upgrade head
```

### 9. Seed Templates (Optional)

```bash
# Seed the 13 production templates
cd apps/api
DATABASE_URL="..." .venv/bin/python -m ceq_api.scripts.seed_db
```

### 10. Configure GitHub Secrets

In GitHub repo Settings > Secrets and variables > Actions:

| Secret | Value |
|--------|-------|
| `KUBECONFIG_BASE64` | Base64-encoded kubeconfig for k3s cluster |

```bash
# Get production kubeconfig (if not already present)
# From enclii repo:
cd /path/to/enclii
./scripts/deploy-production.sh kubeconfig

# Or if you have the kubeconfig already:
# Generate the base64 kubeconfig (macOS)
cat ~/.kube/config | base64 > kubeconfig.b64

# Or on Linux:
cat ~/.kube/config | base64 -w 0 > kubeconfig.b64

# Copy contents to GitHub secret via CLI:
gh secret set KUBECONFIG_BASE64 < kubeconfig.b64

# Or manually paste in GitHub UI:
# https://github.com/madfam-io/ceq/settings/secrets/actions
```

### 11. Deploy via GitHub Actions

```bash
# Push to main triggers deployment
git push origin main

# Or manually trigger
gh workflow run deploy.yaml
```

### 12. Verify Deployment

```bash
# Check pods
kubectl get pods -n ceq

# Check services
kubectl get svc -n ceq

# Test endpoints
curl https://api.ceq.lol/health
curl https://ceq.lol/
```

---

## Troubleshooting

### HTTP 530 Error / Error 1033

This means the Cloudflare tunnel cannot reach the origin server. Common causes:

1. **Infrastructure not deployed**: The k8s cluster doesn't exist
2. **Pods not running**: Check `kubectl get pods -n ceq`
3. **Service not created**: Check `kubectl get svc -n ceq`
4. **Cloudflared not running**: Check `kubectl logs -n ceq deployment/cloudflared`

### API not starting

```bash
kubectl logs -n ceq deployment/ceq-api
```

Common issues:
- Missing environment variables
- Database connection failed
- Redis connection failed

### Database connection issues

```bash
# Verify DATABASE_URL format
# Must use: postgresql+asyncpg:// (not postgres://)
```

### Auth callback not working

1. Verify redirect URI in Janua matches exactly
2. Check CORS allowed origins
3. Verify client_id matches in both Janua and Studio config

### Cloudflared tunnel issues

```bash
kubectl logs -n ceq deployment/cloudflared
```

---

## Architecture Reference

```
                    Cloudflare Edge
                          │
                    ┌─────┴─────┐
                    │  Tunnel   │
                    │  ceq-prod │
                    └─────┬─────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   ceq.lol          api.ceq.lol       ws.ceq.lol
        │                 │                 │
        ▼                 ▼                 │
  ┌──────────┐      ┌──────────┐           │
  │  Studio  │      │   API    │◄──────────┘
  │  :5801   │      │  :5800   │
  └──────────┘      └────┬─────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
              ▼          ▼          ▼
         PostgreSQL   Redis     R2 Storage
         (Ubicloud)   (Shared)  (Cloudflare)
```

---

## Port Allocation

Per [PORT_ALLOCATION.md](https://github.com/madfam-io/solarpunk-foundry/blob/main/docs/PORT_ALLOCATION.md):

| Service | Port |
|---------|------|
| API | 5800 |
| Studio | 5801 |
| Workers | 5810-5819 |
| WebSocket | 5820 |

---

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/deploy.yaml`) handles:

1. **Build API Image**: Push to ghcr.io/madfam/ceq-api
2. **Build Studio Image**: Push to ghcr.io/madfam/ceq-studio
3. **Deploy to K8s**: Apply kustomize manifests
4. **Run Migrations**: Execute alembic upgrade
5. **Health Check**: Verify endpoints respond

Triggered by:
- Push to `main` branch (paths: `apps/**`, `infrastructure/**`)
- Manual dispatch via `gh workflow run deploy.yaml`

---

## Secrets Reference

### secrets.prod.yaml Structure

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ceq-secrets
  namespace: ceq
stringData:
  # Database (Ubicloud PostgreSQL)
  database-url: "postgresql+asyncpg://ceq:PASSWORD@HOST:5432/ceq_production"

  # Redis (Shared MADFAM Redis Sentinel, DB 14)
  redis-url: "redis://:PASSWORD@redis-0.redis-headless.enclii-production.svc.cluster.local:6379/14"

  # Cloudflare R2 (ceq-assets bucket)
  r2-endpoint: "https://12f1353f7819865c56161ce00297668e.r2.cloudflarestorage.com"
  r2-access-key: "51844af3c4cbda516895116372ec3b38"
  r2-secret-key: "..."
  r2-bucket: "ceq-assets"

  # Janua OAuth
  janua-client-id: "jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk"
  janua-client-secret: "..."
```

---

## Related Documentation

| Document | Location |
|----------|----------|
| CEQ README | [/README.md](../README.md) |
| CEQ Agent Instructions | [/CLAUDE.md](../CLAUDE.md) |
| CEQ PRD | [/docs/PRD.md](./PRD.md) |
| Enclii Deployment | [/path/to/enclii/CLAUDE.md](../../enclii/CLAUDE.md) |
| Port Allocation | [solarpunk-foundry/PORT_ALLOCATION.md](https://github.com/madfam-io/solarpunk-foundry/blob/main/docs/PORT_ALLOCATION.md) |
