# CEQ API

FastAPI backend for Creative Entropy Quantized — ComfyUI workflow orchestration and job management.

## Overview

The CEQ API handles:
- Workflow CRUD and versioning
- Job queue management (Redis)
- Asset indexing and search
- Output management and publishing
- Integration with GPU workers via Vast.ai/Furnace

**Port:** 5800
**Domain:** api.ceq.lol

## Quick Start

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run database migrations
alembic upgrade head

# Run development server
uvicorn ceq_api.main:app --port 5800 --reload
```

## API Endpoints

### Workflows

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/workflows` | Create workflow |
| `GET` | `/v1/workflows` | List workflows |
| `GET` | `/v1/workflows/{id}` | Get workflow |
| `PUT` | `/v1/workflows/{id}` | Update workflow |
| `DELETE` | `/v1/workflows/{id}` | Delete workflow |
| `POST` | `/v1/workflows/{id}/run` | Execute workflow |

### Jobs

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/jobs` | List jobs |
| `GET` | `/v1/jobs/{id}` | Get job status |
| `DELETE` | `/v1/jobs/{id}` | Cancel job |
| `WS` | `/v1/jobs/{id}/stream` | Real-time updates |

### Templates

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/templates` | List templates |
| `GET` | `/v1/templates/{id}` | Get template |
| `POST` | `/v1/templates/{id}/fork` | Fork to workflow |
| `POST` | `/v1/templates/{id}/run` | Run template directly |

Templates tagged `pro` or `premium` require a paid Janua role (`pro`,
`premium`, `studio`, or CEQ/plan/tier-prefixed variants) or `admin` before
`fork`/`run`. Workflows derived from premium templates enforce the same check
on `/v1/workflows/{id}/run`, so fork-then-run cannot bypass the gate.

### Assets

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/assets` | List assets |
| `POST` | `/v1/assets` | Upload asset |
| `GET` | `/v1/assets/{id}` | Get asset |

### Outputs

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/outputs` | List outputs |
| `GET` | `/v1/outputs/{id}` | Get output |
| `POST` | `/v1/outputs/{id}/publish` | Publish to channel |

### Credits

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/v1/credits/balance` | user | Current authenticated user's credit balance |
| `GET` | `/v1/credits/ledger` | user | Paginated authenticated user's credit ledger |
| `POST` | `/v1/credits/grants` | admin | Idempotently grant credits to a Janua user |

Credit ledger entries are append-only integer amounts. Positive values grant or
refund credits; negative values consume credits. Every entry carries an
`idempotency_key` so retries cannot double-grant or double-charge.

Render-path credit debits are implemented behind
`RENDER_CREDIT_DEBITS_ENABLED=false` by default. When enabled, `/v1/render/*`
cache misses require enough balance and append exactly one debit keyed by user,
template, and render hash after a successful R2 cache write. Cache hits do not
debit credits.

### Render (generative assets)

Deterministic, cached renders — same input returns the same URL (R2 cache).
Use these endpoints when a consumer needs an asset URL to cache on its own
records (e.g. card thumbnails on Rondelio card records).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/render/card` | Render card-standard thumbnail (512×768 PNG) |
| `POST` | `/v1/render/thumbnail` | Generic render; caller supplies template name |
| `POST` | `/v1/render/audio` | Render audio asset (`audio/wav`). Default template: `tone-beep` — parametric sine + ADSR envelope |
| `POST` | `/v1/render/3d` | Render 3D asset (`model/gltf-binary`). Default template: `card-plate` — parametric rounded-rectangle plate |
| `GET` | `/v1/render/templates` | List available templates + versions |

Request shape:
```json
{"template": "card-standard", "data": {"title": "...", "accent": "#...", ...}}
```

Response shape (same for cache hit + miss):
```json
{
  "url": "https://cdn.../render/card-standard/<hash>.png",
  "storage_uri": "r2://ceq-assets/render/card-standard/<hash>.png",
  "hash": "<sha256>",
  "template": "card-standard",
  "template_version": "1",
  "content_type": "image/png",
  "cached": true
}
```

Clients should prefer the `@ceq/sdk` package (`packages/sdk`) over raw HTTP.

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | | AsyncPG connection string |
| `REDIS_URL` | Yes | | Redis connection (DB 14) |
| `JANUA_ENABLED` | No | `true` | Enable Janua auth |
| `JANUA_URL` | If auth enabled | | Janua API URL |
| `R2_ENDPOINT` | Yes | | Cloudflare R2 endpoint |
| `R2_ACCESS_KEY` | Yes | | R2 access key ID |
| `R2_SECRET_KEY` | Yes | | R2 secret access key |
| `R2_BUCKET` / `R2_BUCKET_NAME` | Yes | `ceq-assets` | R2 bucket name |
| `JOB_COMPLETION_CALLBACK_TOKEN` | Production / workers | | Shared token required for worker completion callbacks |
| `JOB_COMPLETION_DEAD_LETTER_KEY` | No | `ceq:jobs:completion:dead` | Redis list for exhausted worker completion callback payloads |
| `JOB_WEBHOOK_SECRET` | If `webhook_url` is used | | HMAC signing secret for user job completion webhooks |
| `JOB_WEBHOOK_TIMEOUT_SECONDS` | No | `5.0` | Per-attempt webhook HTTP timeout |
| `JOB_WEBHOOK_MAX_ATTEMPTS` | No | `3` | Webhook delivery attempts for retryable failures |
| `JOB_WEBHOOK_RETRY_BACKOFF_SECONDS` | No | `1.0` | Linear retry backoff base in seconds |
| `MAX_ACTIVE_JOBS_PER_USER` | No | `5` | Queued/running job cap per user; set `0` to disable |

Worker completion callback notes:

- Workers retry retryable `POST /v1/jobs/{job_id}/outputs/report` failures and
  write exhausted payloads to Redis `ceq:jobs:completion:dead`.
- Admins can inspect/replay/discard exhausted completion callbacks through
  `/v1/operations/completion-dead-letters`; replay uses
  `JOB_COMPLETION_CALLBACK_TOKEN` and removes the Redis item only after a
  successful upstream callback response.
- `GET /v1/operations/status` exposes admin-only acceptance signals for
  runtime secrets, Alembic revision, queue depth, processing depth, and
  completion dead-letter depth.
- `DELETE /v1/jobs/{job_id}` records `cancel_requested=true` in Redis and
  publishes a per-job cancel control message for active workers.
- Late non-cancelled worker reports cannot overwrite an already-cancelled job.
- New GPU job submissions fail with `429` when the user reaches the active
  queued/running job cap. Free/default users use `MAX_ACTIVE_JOBS_PER_USER`;
  pro, studio, and admin roles use their plan-specific cap variables.
- `outputs` has a DB-level uniqueness guard on `(job_id, storage_uri)`.
- `/metrics` includes CEQ counters for worker completion reports, output
  persistence, cancellations, dead-letter replay outcomes, and user webhook
  delivery outcomes.

### Example .env

```bash
# Database (Ubicloud PostgreSQL)
DATABASE_URL=postgresql+asyncpg://ceq:password@host:5432/ceq_production

# Redis (DB 14 per PORT_ALLOCATION.md)
REDIS_URL=redis://:password@localhost:6379/14

# Janua Authentication
JANUA_ENABLED=true
JANUA_URL=https://api.janua.dev

# Cloudflare R2 Storage
R2_ENDPOINT=https://12f1353f7819865c56161ce00297668e.r2.cloudflarestorage.com
R2_ACCESS_KEY=51844af3c4cbda516895116372ec3b38
R2_SECRET_KEY=your-secret-key
R2_BUCKET=ceq-assets
# R2_BUCKET_NAME=ceq-assets also works and is used by k8s secrets.

# Worker completion callback
JOB_COMPLETION_CALLBACK_TOKEN=dev-shared-worker-callback-token

# User job completion webhooks
JOB_WEBHOOK_SECRET=dev-shared-user-webhook-secret
```

## Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

## Project Structure

```
apps/api/
├── src/ceq_api/
│   ├── main.py           # FastAPI application entry
│   ├── config.py         # Settings and environment
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── routers/          # API route handlers
│   ├── services/         # Business logic
│   │   ├── execution.py  # Workflow execution
│   │   ├── storage.py    # R2 storage
│   │   └── queue.py      # Redis queue
│   └── dependencies/     # FastAPI dependencies
├── alembic/              # Database migrations
├── tests/                # Test suite
└── pyproject.toml        # Package configuration
```

## Authentication

CEQ uses Janua for authentication:

```python
from fastapi import Depends
from ceq_api.dependencies.auth import get_current_user

@router.get("/protected")
async def protected_route(user = Depends(get_current_user)):
    return {"user_id": user.id}
```

JWT tokens are validated against Janua's JWKS endpoint.

## Monetization gating (InterestGate)

CEQ is still pre-checkout, but premium template execution now has an API-side
guard. Templates tagged `pro` or `premium` require a paid/admin Janua role for
direct template `fork`/`run`, synthesis-selected premium templates, and
premium-origin workflow runs.

The studio still uses the **InterestGate** pattern for demand capture: gated UI
is wrapped in `<InterestGate featureKey="..." variant="overlay">` (see
`apps/studio/src/components/InterestGate.tsx`), which shows an email-capture
form. InterestGate does not add checkout to `/v1/render/*`, but the render API
itself is still Janua-authenticated in production. Live public checks on
2026-06-01 returned 401 for unauthenticated `/v1/render/card`.

### Endpoint

| Method | Endpoint | Auth | Rate limit | Description |
|--------|----------|------|-----------|-------------|
| `POST` | `/v1/interest/` | none | 10/hour per IP | Capture email + feature_key (+ optional wishlist) |

Responses:
- `201 Created` `{"status": "registered"}` — first capture for `(email, feature_key)`
- `200 OK` `{"status": "already_registered"}` — duplicate; backfills missing fields
- `400/422` — invalid email or unknown `feature_key`
- `429` — rate limit exceeded
- `503` — capture disabled (`INTEREST_ENABLED=false`)

Allowed `feature_key` values are listed in
`apps/api/src/ceq_api/routers/interest.py::ALLOWED_FEATURES`. Add new keys
there when you wire up new gates and keep them in sync with
`apps/studio/src/lib/feature-labels.ts`.

### Storage

Captures land in the `feature_interest` table (see migration
`8a3f1c4e5d20_add_feature_interest.py` and model
`ceq_api/models/feature_interest.py`). Indexed on `(email, feature_key)` for
the upsert lookup and on `(feature_key, created_at)` for analytics.

### CRM dispatch

On every successful **new** registration the API enqueues a
`dispatch_interest_to_crm` background task that POSTs an HMAC-SHA256-signed
payload to `CRM_WEBHOOK_URL`. When either `CRM_WEBHOOK_URL` or
`CRM_WEBHOOK_SECRET` is unset, the dispatch is a silent no-op — the DB row
is still the source of truth. Phynd-CRM receives:

```json
{
  "event": "interest.created",
  "timestamp": "2026-04-25T12:00:00+00:00",
  "source": "ceq",
  "data": {
    "email": "user@example.com",
    "feature_key": "premium_render",
    "wishlist": {"text": "..."} ,
    "janua_user_id": null,
    "source_page": "templates/3d",
    "created_at": "2026-04-25T12:00:00+00:00"
  }
}
```

Verify with:

```python
expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
assert request.headers["X-Webhook-Signature"] == f"sha256={expected}"
```

### Environment

| Variable | Default | Notes |
|----------|---------|-------|
| `INTEREST_ENABLED` | `true` | Set to `false` to hard-disable capture (returns 503) |
| `CRM_WEBHOOK_URL` | `""` | e.g. `https://crm.madfam.io/api/webhooks/ceq`. Empty = no-op |
| `CRM_WEBHOOK_SECRET` | `""` | 32-byte hex secret shared with Phynd-CRM. Empty = no-op |
| `CRM_WEBHOOK_TIMEOUT_SECONDS` | `5.0` | Per-request HTTP timeout |
| `RENDER_CREDIT_DEBITS_ENABLED` | `false` | Enable credit debit enforcement on `/v1/render/*` cache misses |
| `RENDER_CREDIT_COST_CARD` | `5` | Credit cost for card/thumbnail cache misses |
| `RENDER_CREDIT_COST_AUDIO` | `3` | Credit cost for audio cache misses |
| `RENDER_CREDIT_COST_3D` | `10` | Credit cost for 3D cache misses |
| `GPU_JOB_CREDIT_DEBITS_ENABLED` | `false` | Enable credit debit/refund enforcement for GPU job submissions |
| `GPU_JOB_CREDIT_COST_IMAGE` | `25` | Credit cost for image/social GPU jobs |
| `GPU_JOB_CREDIT_COST_VIDEO` | `75` | Credit cost for video GPU jobs |
| `GPU_JOB_CREDIT_COST_3D` | `50` | Credit cost for 3D/synthesis GPU jobs |
| `GPU_JOB_CREDIT_COST_DEFAULT` | `25` | Fallback GPU job credit cost |
| `MAX_ACTIVE_JOBS_PRO` | `10` | Active queued/running GPU jobs for `pro`/`premium` roles |
| `MAX_ACTIVE_JOBS_STUDIO` | `25` | Active queued/running GPU jobs for `studio` roles |
| `MAX_ACTIVE_JOBS_ADMIN` | `0` | Admin active-job cap; `0` disables the cap |

### Flipping to paid checkout later

When WTP signal is sufficient and billing is wired up:

1. Replace `<InterestGate>` wrappers in the studio with a real checkout/tier
   gate (e.g. a `<TierGate>` similar to tezca's pattern).
2. Connect Dhanam checkout to the credit ledger, fund balances, and enable
   render/GPU debit flags for paid cohorts.
3. Keep `POST /v1/interest/` available as a **fallback** for "not ready to
   buy" users — it's still useful WTP signal post-launch.
4. Migrate the existing `feature_interest` rows into the CRM as a warm
   waitlist; email them announcing checkout availability.
5. Add a deprecation log line to `register_interest` when the feature_key
   has a paid SKU available, so we can spot rows that should have hit
   checkout instead.

The existing `/v1/render/*` endpoints remain stable under all gating
strategies. They are an authenticated evaluation/integration surface and the
contract Rondelio + other internal consumers depend on (see `@ceq/sdk`).

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/

# Linting
ruff check src/

# Format code
ruff format src/
```

## Docker

```bash
# Build image
docker build -t ceq-api:latest .

# Run container
docker run -p 5800:5800 --env-file .env ceq-api:latest
```

## Production Deployment

The API is deployed through the CEQ GitOps workflow: GitHub Actions builds
images, commits immutable digests to `infrastructure/k8s/kustomization.yaml`,
and ArgoCD reconciles production. Routine production operations are Enclii-first.
See [docs/PRODUCTION_DEPLOYMENT.md](../../docs/PRODUCTION_DEPLOYMENT.md).

```bash
# Break-glass only if Enclii or the operations API is unavailable:
kubectl get pods -n ceq -l app=ceq-api
kubectl logs -n ceq deployment/ceq-api
kubectl port-forward -n ceq deployment/ceq-api 5800:5800
```

## License

PROPRIETARY - MADFAM
