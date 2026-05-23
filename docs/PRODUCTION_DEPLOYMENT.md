# CEQ Production Deployment Guide

> [!IMPORTANT]
> MADFAM-ENCLII-FIRST-LEGACY-RAW v1: This document contains legacy raw infrastructure command examples.
> Routine production operations must use Enclii web, API, or CLI. Treat raw
> `kubectl`, `helm`, SSH, provider CLI/API, `docker exec`, and direct container
> access as platform bootstrap or documented break-glass only, and record any
> missing Enclii adapter gap.


> Deploy CEQ to production at ceq.lol via Enclii infrastructure

## Prerequisites

- Access to Cloudflare Zero Trust dashboard
- Access to Janua admin at https://auth.madfam.io/admin
- Access to Ubicloud console for PostgreSQL
- kubectl configured for k3s cluster
- GitHub repo write access for secrets
- Terraform installed (`brew install terraform`)

## Deployment Status (2026-05-14)

| Step | Status | Notes |
|------|--------|-------|
| Janua OAuth Client | Action required | Active client currently rejected by Janua; register/rotate for `app.ceq.lol` |
| Cloudflare Tunnel Routes | Done | ceq.lol, app.ceq.lol, api.ceq.lol, ws.ceq.lol |
| R2 Bucket + Token | Done | `ceq-assets` with Object Read & Write |
| secrets.local.yaml | Done | R2 + OAuth done, DB/Redis configured |
| Enclii Infrastructure | Done | Terraform applied |
| Ubicloud Database | Done | ceq_production database created |
| Redis Password | Done | Redis configured |
| GitHub Actions Secret | Done | KUBECONFIG_BASE64 applied |
| Studio Auth Gate | Done | `app.ceq.lol` no-cookie gate verified with public smoke |
| Deploy + Verify | Done | GitOps deploy `25853708026` succeeded; digest commit `1eaf6a6` |



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

### 3. Register OAuth Client in Janua (Action Required)

> **Operator runbook:** See [`docs/JANUA_OPERATOR.md`](./JANUA_OPERATOR.md) for the full checklist, verification commands, and acceptance gates.  
> **Janua agent handoff:** [`docs/JANUA_AGENT_HANDOFF.md`](./JANUA_AGENT_HANDOFF.md)  
> **Capped GA demo:** [`docs/GA_DEMO_DEFINITION.md`](./GA_DEMO_DEFINITION.md)

The Studio uses Janua's OIDC discovery endpoints:

- Authorization: `https://auth.madfam.io/api/v1/oauth/authorize`
- Token: `https://auth.madfam.io/api/v1/oauth/token`
- UserInfo: `https://auth.madfam.io/api/v1/oauth/userinfo`

As of 2026-05-14, live Janua returns `invalid_client: Unknown client_id` for
`jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk`. Register that client again or rotate
CEQ to a new client and update `NEXT_PUBLIC_JANUA_CLIENT_ID` plus
`JANUA_CLIENT_SECRET` before declaring Studio login healthy.

The Studio route is now server-gated with CEQ session cookies:

- `app.ceq.lol/` redirects unauthenticated browsers to
  `/login?returnTo=%2F` before rendering the Studio shell.
- `/login` redirects to Janua using the OIDC endpoints above.
- `/auth/callback` exchanges the authorization code, sets httpOnly CEQ session
  cookies, and preserves the existing browser access-token bridge for direct
  CEQ API calls.
- `/api/auth/session` bootstraps the client from the httpOnly session cookie
  and refreshes via Janua when the refresh cookie is present.
- `/api/auth/logout` clears CEQ session cookies before Janua logout.
- `/api/proxy` now forwards Studio API calls through CEQ session-aware BFF logic,
  attaching bearer credentials from `/api/auth/session` to the internal API.
- REST workflows were moved off direct browser token usage; the legacy direct
  token path remains only as a compatibility layer (e.g. websocket bootstrap flows).

| Field | Value |
|-------|-------|
| **Name** | CEQ Studio |
| **Client ID** | `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk` |
| **Client Secret** | Stored in `infrastructure/k8s/secrets.local.yaml` |
| **Grant Types** | `authorization_code`, `refresh_token` |
| **Redirect URIs** | `https://app.ceq.lol/auth/callback`, `http://localhost:5801/auth/callback` |
| **Scopes** | `openid`, `profile`, `email` |

### 4. Create Cloudflare R2 Bucket (Done)

**Completed 2026-04-30.** Resources created:

| Resource | Value |
|----------|-------|
| **Bucket** | `ceq-assets` (Western North America) |
| **Token** | `CEQ R2 Token` (Object Read & Write) |
| **Access Key** | Stored in `infrastructure/k8s/secrets.local.yaml` |
| **Secret Key** | Stored in `infrastructure/k8s/secrets.local.yaml` |
| **Endpoint** | `https://12f1353f7819865c56161ce00297668e.r2.cloudflarestorage.com` |

### 5. Configure Tunnel Routes (Done)

**Completed 2026-04-30.** Tunnel: `ceq-prod` (ID: `0de376f0-dd76-40ab-af58-1a5d63eb9b11`)

| Public Hostname | Service | Port |
|-----------------|---------|------|
| `ceq.lol` | `http://ceq-studio.ceq.svc.cluster.local` | 5801 |
| `app.ceq.lol` | `http://ceq-studio.ceq.svc.cluster.local` | 5801 |
| `api.ceq.lol` | `http://ceq-api.ceq.svc.cluster.local` | 5800 |
| `ws.ceq.lol` | `http://ceq-api.ceq.svc.cluster.local` | 5800 |

`ceq.lol` is the marketing/demo surface. `app.ceq.lol` is the authenticated
Studio surface. WebSocket support is enabled for `ws.ceq.lol`.

### 6. Configure Production Secrets

```bash
# Copy the template
cp infrastructure/k8s/secrets.yaml infrastructure/k8s/secrets.local.yaml

# Edit with real values
vim infrastructure/k8s/secrets.local.yaml

# Apply to cluster
kubectl apply -f infrastructure/k8s/secrets.local.yaml
```

Required values:
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis URL (DB 14)
- `R2_ENDPOINT`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_BUCKET_NAME`: Cloudflare R2 credentials
- `JOB_COMPLETION_CALLBACK_TOKEN`: Shared API/worker token for `POST /v1/jobs/{job_id}/outputs/report`
- `JOB_WEBHOOK_SECRET`: HMAC signing secret for user-provided job completion webhooks

Callback token rules:
- Generate a high-entropy secret and store the exact same value for API and workers.
- The API refuses worker completion callbacks in production when this value is missing.
- The worker deployment maps this secret into `API_JOB_COMPLETION_TOKEN`.
- Workers retry retryable callback failures and push exhausted payloads to
  Redis `ceq:jobs:completion:dead`.
- Rotate by updating the secret and rolling API + worker pods together.

Job webhook rules:
- Generate a separate high-entropy `JOB_WEBHOOK_SECRET`; do not reuse worker callback tokens.
- CEQ signs user webhook payloads with `X-CEQ-Signature: sha256=<hmac>`.
- If this value is missing, jobs still complete but webhook delivery is skipped and recorded in job metadata.

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

Use Enclii web/API/CLI first for routine rollout verification. The raw
commands below are legacy/break-glass references only.

```bash
# Check pods
kubectl get pods -n ceq

# Check services
kubectl get svc -n ceq

# Test endpoints
curl https://api.ceq.lol/health
curl https://ceq.lol/
```

Stability smoke after the 2026-05 output-contract remediation:

1. Submit a real workflow or template run from Studio.
2. Confirm the job enters Redis DB 14 and is claimed by a worker.
3. Confirm the worker uploads output descriptors with `filename`, `storage_uri`, `file_type`, `file_size_bytes`, and optional `preview_url`.
4. Confirm `POST /v1/jobs/{job_id}/outputs/report` persists final job status and output rows.
5. Confirm `/v1/jobs/{job_id}` and `/v1/outputs` show the same output metadata.
6. Confirm the Studio gallery opens `public_url`/preview URLs in the browser.
7. Cancel one running GPU job and confirm the worker reports durable `cancelled`.
8. Confirm the migration chain includes `20260514_outputs_job_storage_unique` and the
   `outputs(job_id, storage_uri)` uniqueness guard is present.

The release is not considered stable until the full Studio -> API -> Redis -> worker -> R2 -> callback -> PostgreSQL -> gallery loop has passed once in the target environment.

Additional 2026-05-14 wave gates:

1. Confirm `JOB_COMPLETION_CALLBACK_TOKEN` and `JOB_WEBHOOK_SECRET` are present through `GET /v1/operations/status`.
2. Confirm the PreSync migration job applied `20260514_outputs_job_storage_unique` through the same operations status response.
3. Confirm exhausted worker callback payloads are inspectable through `GET /v1/operations/completion-dead-letters`.
4. Replay or discard any exhausted callback payloads through `/v1/operations/completion-dead-letters/{index}`.
5. Cancel one actively running GPU job and verify the API remains `cancelled`.
6. Run at least one image, video, audio, and 3D/model template and confirm Studio gallery rendering/opening behavior.
7. Confirm the active deploy commit pins API, Studio, and Worker by digest.

The API-level smoke runner exercises the same durable completion path without
raw cluster access:

```bash
CEQ_AUTH_TOKEN="<janua-jwt>" \
CEQ_TEMPLATE_ID="<template-uuid>" \
CEQ_TEMPLATE_PARAMS_JSON='{}' \
scripts/production-smoke.sh
```

Admin acceptance status can be included in the same run:

```bash
CEQ_AUTH_TOKEN="<janua-jwt>" \
CEQ_ADMIN_AUTH_TOKEN="<admin-janua-jwt>" \
CEQ_RUN_OPERATIONS_STATUS=true \
CEQ_REQUIRE_WEBHOOK_SECRET=true \
CEQ_EXPECT_MAX_COMPLETION_DEAD_LETTERS=0 \
CEQ_EXPECT_ALEMBIC_REVISION="20260514_outputs_job_storage_unique" \
CEQ_TEMPLATE_ID="<template-uuid>" \
scripts/production-smoke.sh
```

Multi-modal and cancellation acceptance can be run without raw Redis or pod
access:

```bash
CEQ_AUTH_TOKEN="<janua-jwt>" \
CEQ_ADMIN_AUTH_TOKEN="<admin-janua-jwt>" \
CEQ_RUN_OPERATIONS_STATUS=true \
CEQ_EXPECT_MAX_COMPLETION_DEAD_LETTERS=3 \
CEQ_TEMPLATE_SMOKES_JSON='[
  {"label":"image","template_id":"<image-template-id>","params":{}},
  {"label":"video","template_id":"<video-template-id>","params":{}},
  {"label":"audio","template_id":"<audio-template-id>","params":{}},
  {"label":"3d","template_id":"<3d-template-id>","params":{}}
]' \
CEQ_RUN_CANCEL_SMOKE=true \
CEQ_CANCEL_TEMPLATE_ID="<long-running-template-id>" \
scripts/production-smoke.sh
```

For public edge checks only:

```bash
CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh
```

The public-only smoke checks the landing/app host split as well as API health:

- `ceq.lol` serves the public landing/demo surface.
- `ceq.lol/login` redirects to `app.ceq.lol/login`.
- `app.ceq.lol/landing` redirects back to `ceq.lol`.
- `app.ceq.lol/` redirects no-cookie users to `app.ceq.lol/login`. Keep the
  default auth-gate assertion enabled except during a documented rollback.

Last verified after the auth-gate deploy on 2026-05-14:

```bash
CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh
```

Result: API health `ok`, `ceq.lol` HTTP `200`, marketing login handoff `307`,
app landing handoff `307`, and unauthenticated app gate `307` to
`https://app.ceq.lol/login?returnTo=%2F`.

---

## Troubleshooting

### HTTP 530 Error / Error 1033

This means the Cloudflare tunnel cannot reach the origin server. Common causes:

1. **Infrastructure not deployed**: The k8s cluster doesn't exist
2. **Pods not running**: use Enclii workload diagnostics first; raw pod checks are break-glass only
3. **Service not created**: use Enclii service diagnostics first; raw service checks are break-glass only
4. **Cloudflared not running**: check the platform tunnel through Enclii first

### API not starting

```bash
enclii ops pods diagnose --namespace ceq --workload ceq-api
```

Common issues:
- Missing environment variables
- Missing `JOB_COMPLETION_CALLBACK_TOKEN`
- Database connection failed
- Redis connection failed

### Worker completions not persisting

1. Use `GET /v1/operations/status` to verify `JOB_COMPLETION_CALLBACK_TOKEN` is configured and Redis is reachable.
2. Use `GET /v1/operations/completion-dead-letters` to inspect exhausted callback payloads.
3. Replay a known-good payload with `POST /v1/operations/completion-dead-letters/{index}/replay`.
4. Use Enclii workload diagnostics for API/worker logs and network path checks.
5. Confirm NetworkPolicies allow intra-namespace traffic and egress to R2/Redis.

Raw `kubectl`/Redis inspection is break-glass only when Enclii or the
operations API is unavailable; record the missing Enclii adapter gap if that is
required.

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

1. **Build API Image**: Push to ghcr.io/madfam-org/ceq-api
2. **Build Studio Image**: Push to ghcr.io/madfam-org/ceq-studio
3. **Build Worker Image**: Push to ghcr.io/madfam-org/ceq-worker
4. **Deploy to K8s**: Commit image digests into kustomization and let ArgoCD reconcile
5. **Run Migrations**: Execute Alembic as ArgoCD PreSync migration job
6. **Health Check**: Verify endpoints respond

Triggered by:
- Push to `main` branch (paths: `apps/**`, `infrastructure/**`)
- Manual dispatch via `gh workflow run deploy.yaml`

---

## Secrets Reference

### secrets.local.yaml Structure

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ceq-secrets
  namespace: ceq
stringData:
  # Database (Ubicloud PostgreSQL)
  DATABASE_URL: "postgresql+asyncpg://ceq:PASSWORD@HOST:5432/ceq_production"

  # Redis (Shared MADFAM Redis Sentinel, DB 14)
  REDIS_URL: "redis://:PASSWORD@redis-0.redis-headless.enclii-production.svc.cluster.local:6379/14"

  # Cloudflare R2 (ceq-assets bucket)
  R2_ENDPOINT: "https://12f1353f7819865c56161ce00297668e.r2.cloudflarestorage.com"
  R2_ACCESS_KEY: "..."
  R2_SECRET_KEY: "..."
  R2_BUCKET_NAME: "ceq-assets"
  # Optional alias if your process expects it:
  # R2_BUCKET: "ceq-assets"

  # Worker callback + user webhook signing
  JOB_COMPLETION_CALLBACK_TOKEN: "..."
  JOB_WEBHOOK_SECRET: "..."

  # Janua OAuth
  JANUA_CLIENT_ID: "jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk"
  JANUA_CLIENT_SECRET: "..."
``` 

---

## Related Documentation

| Document | Location |
|----------|----------|
| CEQ README | [/README.md](../README.md) |
| CEQ Agent Instructions | [/CLAUDE.md](../CLAUDE.md) |
| CEQ PRD | [/docs/PRD.md](./PRD.md) |
| CEQ Stability Roadmap | [/docs/CEQ_STABILITY_ROADMAP.md](./CEQ_STABILITY_ROADMAP.md) |
| Capped GA Demo Definition | [/docs/GA_DEMO_DEFINITION.md](./GA_DEMO_DEFINITION.md) |
| Janua Operator Guide | [/docs/JANUA_OPERATOR.md](./JANUA_OPERATOR.md) |
| Janua Agent Handoff | [/docs/JANUA_AGENT_HANDOFF.md](./JANUA_AGENT_HANDOFF.md) |
| Enclii Deployment | [/path/to/enclii/CLAUDE.md](../../enclii/CLAUDE.md) |
| Port Allocation | [solarpunk-foundry/PORT_ALLOCATION.md](https://github.com/madfam-io/solarpunk-foundry/blob/main/docs/PORT_ALLOCATION.md) |

---

## Pre-deploy verification (CI)

Before ArgoCD picks up new Studio digests, CI must pass:

| Job | What it guards |
|-----|----------------|
| `Studio · Docker smoke` | Standalone entrypoint at `apps/studio/server.js` + HTTP 200 |
| `Studio · Playwright auth` | Mocked Janua OAuth, session bootstrap, refresh, logout (6 tests) |
| `verify-ci` (deploy workflow) | Deploy waits for CEQ CI green on the commit SHA |

Local equivalents:

```bash
# After building the studio image locally
bash scripts/studio-docker-smoke.sh ceq-studio:local

# Auth E2E (install Chromium once)
cd apps/studio && pnpm exec playwright install chromium && CI=true pnpm test:e2e
```
