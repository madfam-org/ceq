# CEQ API Reference

API documentation for CEQ — Creative Entropy Quantized.

**Base URL:** `https://api.ceq.lol`
**Authentication:** Bearer token (Janua JWT)

## Authentication

Most user-scoped and mutating API requests require a valid JWT token from Janua.
Public exceptions include health checks and template discovery (`GET
/v1/templates`, `GET /v1/templates/{id}`, `GET /v1/templates/categories`).

```bash
curl https://api.ceq.lol/v1/workflows \
  -H "Authorization: Bearer <your-jwt-token>"
```

## Endpoints

### Health Check

```http
GET /health
```

Returns API health status.

**Response:**
```json
{
  "status": "ok",
  "service": "ceq-api",
  "version": "0.1.0"
}
```

---

## Render Assets

The render API is deterministic and content-addressed. In production it
requires a Janua bearer token; unauthenticated requests return `401`.

| Method | Endpoint | Output |
|--------|----------|--------|
| `POST` | `/v1/render/card` | `card-standard` PNG, 512x768 |
| `POST` | `/v1/render/thumbnail` | Generic registered thumbnail template |
| `POST` | `/v1/render/audio` | `tone-beep` WAV, 16-bit PCM at 22.05kHz |
| `POST` | `/v1/render/3d` | `card-plate` GLB |
| `GET` | `/v1/render/templates` | Registered render templates |

Request:
```json
{
  "template": "card-standard",
  "data": {
    "title": "Smoke",
    "accent": "#FF5A3C"
  }
}
```

Response:
```json
{
  "url": "https://...",
  "storage_uri": "r2://ceq-assets/render/card-standard/<hash>.png",
  "hash": "<sha256>",
  "template": "card-standard",
  "template_version": "1",
  "content_type": "image/png",
  "cached": true
}
```

---

## Workflows

### List Workflows

```http
GET /v1/workflows
```

Returns all workflows for the authenticated user.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max results (default: 50) |
| `skip` | int | Pagination offset |
| `tag` | string | Filter by tag |
| `public_only` | bool | Return only public workflows |

**Response:**
```json
{
  "workflows": [
    {
      "id": "uuid",
      "name": "My Workflow",
      "description": "Generates social posts",
      "created_at": "2025-12-10T12:00:00Z",
      "updated_at": "2025-12-10T12:00:00Z",
      "tags": ["social", "sdxl"]
    }
  ],
  "total": 42
}
```

### Get Workflow

```http
GET /v1/workflows/{id}
```

Returns a specific workflow with full details.

**Response:**
```json
{
  "id": "uuid",
  "name": "My Workflow",
  "description": "Generates social posts",
  "workflow_json": { /* ComfyUI workflow */ },
  "input_schema": {
    "type": "object",
    "properties": {
      "prompt": { "type": "string" },
      "seed": { "type": "integer" }
    }
  },
  "created_at": "2025-12-10T12:00:00Z",
  "updated_at": "2025-12-10T12:00:00Z"
}
```

### Create Workflow

```http
POST /v1/workflows
```

Creates a new workflow.

**Request Body:**
```json
{
  "name": "My Workflow",
  "description": "Generates social posts",
  "workflow_json": { /* ComfyUI workflow */ },
  "input_schema": { /* JSON Schema */ },
  "tags": ["social"]
}
```

**Response:** Created workflow object.

### Update Workflow

```http
PUT /v1/workflows/{id}
```

Updates an existing workflow.

**Request Body:** Same as create.

### Delete Workflow

```http
DELETE /v1/workflows/{id}
```

Deletes a workflow.

**Response:** `204 No Content`

### Run Workflow

```http
POST /v1/workflows/{id}/run
```

Executes a workflow and returns a job ID.

New job submissions are capped across queued and running jobs. Free/default
users use `MAX_ACTIVE_JOBS_PER_USER`; `pro`/`premium`, `studio`, and `admin`
roles use `MAX_ACTIVE_JOBS_PRO`, `MAX_ACTIVE_JOBS_STUDIO`, and
`MAX_ACTIVE_JOBS_ADMIN` respectively. `0` disables a cap. When the authenticated
user is at the cap, this endpoint returns `429`.

**Request Body:**
```json
{
  "params": {
    "prompt": "a cosmic nebula, vibrant colors",
    "seed": 42
  }
}
```

**Response:**
```json
{
  "job_id": "uuid",
  "status": "queued",
  "queue_position": 3
}
```

---

## Jobs

### List Jobs

```http
GET /v1/jobs
```

Returns all jobs for the authenticated user.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status_filter` | string | Filter: queued, running, completed, failed, cancelled |
| `limit` | int | Max results (default: 50) |
| `skip` | int | Pagination offset |

**Response:**
```json
{
  "jobs": [
    {
      "id": "uuid",
      "workflow_id": "uuid",
      "status": "completed",
      "queued_at": "2025-12-10T12:00:00Z",
      "started_at": "2025-12-10T12:01:00Z",
      "completed_at": "2025-12-10T12:02:30Z"
    }
  ],
  "total": 100
}
```

### Get Job

```http
GET /v1/jobs/{id}
```

Returns job details including outputs if complete.

**Response:**
```json
{
  "id": "uuid",
  "workflow_id": "uuid",
  "status": "completed",
  "progress": 1.0,
  "current_node": null,
  "error": null,
  "input_params": { "prompt": "...", "seed": 42 },
  "outputs": [
    {
      "id": "uuid",
      "filename": "output.png",
      "storage_uri": "r2://ceq-assets/outputs/job/output.png",
      "public_url": "https://...",
      "file_type": "image/png",
      "file_size_bytes": 524288,
      "width": 512,
      "height": 768,
      "duration_seconds": null,
      "preview_url": "https://..."
    }
  ],
  "output_metadata": {
    "worker_callback_reported_at": "2026-05-14T12:00:00+00:00",
    "webhook_delivery": {"status": "delivered", "attempts": 1}
  },
  "queued_at": "2025-12-10T12:00:00Z",
  "started_at": "2025-12-10T12:00:10Z",
  "completed_at": "2025-12-10T12:02:30Z",
  "gpu_seconds": 12.4,
  "cold_start_ms": 0,
  "worker_id": "ceq-worker-0",
  "brand_message": "Materialized. ✨"
}
```

### Cancel Job

```http
DELETE /v1/jobs/{id}
```

Cancels a queued or running job. CEQ removes queued Redis payloads when the job
has not started. For active worker jobs, the API writes `cancel_requested=true`
to `ceq:job:{id}`, publishes `{"action":"cancel"}` on
`ceq:job:{id}:control`, and workers interrupt ComfyUI before reporting durable
`cancelled` completion.

**Response:** `204 No Content`

### Stream Job Updates (WebSocket)

```
WS /v1/jobs/{id}/stream?token=<janua-jwt>
```

Real-time job progress updates. The WebSocket endpoint requires the Janua JWT
as the `token` query parameter; bearer headers are not available during the
browser WebSocket handshake.

**Messages:**
```json
// Progress update
{
  "type": "progress",
  "step": 15,
  "total_steps": 30,
  "preview_url": "..."
}

// Completion
{
  "type": "complete",
  "outputs": ["https://..."]
}

// Error
{
  "type": "error",
  "message": "Out of VRAM"
}
```

---

## Templates

### List Templates

```http
GET /v1/templates
```

Returns available workflow templates.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `category` | string | Filter: social, video, 3d, utility |

**Response:**
```json
{
  "templates": [
    {
      "id": "uuid",
      "name": "Social Post Generator",
      "category": "social",
      "description": "Generate social media posts",
      "thumbnail_url": "https://...",
      "model_requirements": ["sdxl-base"],
      "vram_requirement_gb": 12
    }
  ]
}
```

### Get Template

```http
GET /v1/templates/{id}
```

Returns template details.

### Fork Template

```http
POST /v1/templates/{id}/fork
```

Creates a new workflow from a template.

**Request Body:**
```json
{
  "name": "My Social Post Workflow"
}
```

**Response:** New workflow object.

### Run Template

```http
POST /v1/templates/{id}/run
```

Runs a template directly and returns a queued job.

Templates tagged `pro` or `premium` require a paid/admin Janua role before
`fork` or `run`. The same entitlement check is applied when running a workflow
derived from a premium template, so direct API callers cannot bypass the Studio
InterestGate by forking first.

Template runs use the same per-user active job cap as workflow runs.

Unentitled response:

```json
{
  "detail": {
    "message": "Template requires Pro or Studio access.",
    "required_entitlement": "paid_template",
    "template_id": "uuid",
    "template_tags": ["premium"]
  }
}
```

---

## Credits

Credit ledger endpoints are authenticated and append-only. Positive amounts
grant/refund credits; negative amounts consume credits. Each ledger entry
requires an `idempotency_key` so retries do not double-apply commercial events.

Render debit enforcement exists behind `RENDER_CREDIT_DEBITS_ENABLED=false` by
default. When enabled, `/v1/render/*` cache misses require enough balance,
append one debit after successful R2 cache write, and return `402` when the user
does not have enough credits. Cache hits do not debit credits.

GPU job debit/refund enforcement exists behind
`GPU_JOB_CREDIT_DEBITS_ENABLED=false` by default. When enabled,
workflow/template/synthesis submissions require enough balance, append one debit
for the queued job, and refund once when the API cancels the job or a worker
reports `failed`/`cancelled`.

### Get Balance

```http
GET /v1/credits/balance
```

Returns the authenticated user's current credit balance.

```json
{
  "user_id": "uuid",
  "org_id": "uuid",
  "balance": 375
}
```

### List Ledger

```http
GET /v1/credits/ledger
```

Returns paginated ledger entries for the authenticated user.

### Grant Credits

```http
POST /v1/credits/grants
```

Admin-only endpoint for pilot grants and support adjustments. Reusing the same
`idempotency_key` with the same payload returns the existing entry; reusing it
with a different payload returns `409`.

```json
{
  "user_id": "uuid",
  "org_id": "uuid",
  "amount": 250,
  "reason": "pilot grant",
  "idempotency_key": "pilot-grant-001",
  "metadata": {
    "source": "support"
  }
}
```

---

## Assets

### List Assets

```http
GET /v1/assets
```

Returns available models, LoRAs, and other assets.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `type` | string | Filter: checkpoint, lora, vae, embedding |

**Response:**
```json
{
  "assets": [
    {
      "id": "uuid",
      "name": "SDXL Base",
      "asset_type": "checkpoint",
      "size_bytes": 6800000000,
      "preview_url": "https://..."
    }
  ]
}
```

### Upload Asset

```http
POST /v1/assets
```

Upload a new asset (multipart form data).

### Get Asset

```http
GET /v1/assets/{id}
```

Returns asset details.

---

## Outputs

### List Outputs

```http
GET /v1/outputs
```

Returns generated outputs.

**Response:**
```json
{
  "outputs": [
    {
      "id": "uuid",
      "job_id": "uuid",
      "filename": "output.png",
      "storage_uri": "r2://ceq-assets/outputs/job/output.png",
      "public_url": "https://...",
      "file_type": "image/png",
      "file_size_bytes": 524288,
      "width": 1024,
      "height": 1024,
      "duration_seconds": null,
      "preview_url": "https://...",
      "metadata": { "seed": 42 },
      "created_at": "2025-12-10T12:00:00Z"
    }
  ]
}
```

### Worker Completion Report

```http
POST /v1/jobs/{id}/outputs/report
```

Internal worker callback. Requires `X-CEQ-Worker-Token` matching the API `JOB_COMPLETION_CALLBACK_TOKEN`; workers send the same value from `API_JOB_COMPLETION_TOKEN`.

**Request Body:**
```json
{
  "status": "completed",
  "progress": 1.0,
  "worker_id": "ceq-worker-0",
  "gpu_seconds": 12.4,
  "outputs": [
    {
      "filename": "output.png",
      "storage_uri": "r2://ceq-assets/outputs/job/output.png",
      "file_type": "image/png",
      "file_size_bytes": 524288,
      "width": 512,
      "height": 768,
      "duration_seconds": null,
      "preview_url": "https://..."
    }
  ]
}
```

Worker callback behavior:

- `completed`, `failed`, and `cancelled` are terminal reports.
- Retryable worker-to-API callback failures are retried by the worker.
- Exhausted worker callback payloads are pushed to Redis
  `ceq:jobs:completion:dead` and marked on `ceq:job:{id}` with
  `callback_dead_lettered=true`.
- If a job is already `cancelled`, a late non-cancelled worker report is
  recorded in metadata and does not overwrite the cancelled status.

If the job was created with `webhook_url`, terminal reports (`completed`,
`failed`, `cancelled`) trigger a signed user webhook delivery.

**User Webhook Headers:**

| Header | Description |
|--------|-------------|
| `X-CEQ-Event` | `job.completed`, `job.failed`, or `job.cancelled` |
| `X-CEQ-Job-ID` | Job UUID |
| `X-CEQ-Timestamp` | ISO-8601 send timestamp |
| `X-CEQ-Signature` | `sha256=<hmac>` over the raw JSON body using `JOB_WEBHOOK_SECRET` |

**User Webhook Payload:**
```json
{
  "event": "job.completed",
  "timestamp": "2026-05-14T12:00:00+00:00",
  "source": "ceq",
  "job": {
    "id": "uuid",
    "workflow_id": "uuid",
    "status": "completed",
    "progress": 1.0,
    "error": null,
    "input_params": {"prompt": "..."},
    "metadata": {"worker_callback_reported_at": "..."},
    "queued_at": "...",
    "started_at": "...",
    "completed_at": "...",
    "worker_id": "ceq-worker-0",
    "gpu_seconds": 12.4,
    "cold_start_ms": 0
  },
  "outputs": [
    {
      "id": "uuid",
      "filename": "output.png",
      "storage_uri": "r2://ceq-assets/outputs/job/output.png",
      "public_url": "https://...",
      "file_type": "image/png",
      "file_size_bytes": 524288,
      "width": null,
      "height": null,
      "duration_seconds": null,
      "preview_url": "https://...",
      "metadata": {}
    }
  ]
}
```

Delivery status is stored on the job under
`output_metadata.webhook_delivery`.

## Admin Operations

All operations endpoints require a Janua user with the `admin` role.

### Runtime Status

```http
GET /v1/operations/status
```

Returns production acceptance signals without raw cluster access: environment,
app version, R2/auth/secret readiness, current Alembic revision when readable,
and Redis queue/dead-letter lengths.

Requires an authenticated Janua user with the `admin` role.

Example response:

```json
{
  "environment": "production",
  "redis": {
    "reachable": true,
    "pending_jobs": 2,
    "processing_jobs": 1,
    "completion_dead_letters": 0
  },
  "r2_configured": true,
  "callback_token_configured": true,
  "webhook_secret_configured": false,
  "app_version": "0.1.0",
  "alembic_revision": "20260514_outputs_job_storage_unique"
}
```

### Completion Dead Letters

```http
GET /v1/operations/completion-dead-letters?skip=0&limit=50
POST /v1/operations/completion-dead-letters/{index}/replay
DELETE /v1/operations/completion-dead-letters/{index}
```

Workers push exhausted completion callback payloads to Redis
`ceq:jobs:completion:dead`. Admins can list them, replay one payload back to its
stored callback URL with the configured `JOB_COMPLETION_CALLBACK_TOKEN`, or
discard a payload after manual handling. Successful replay removes the exact
Redis list item and marks the job Redis hash with `callback_replayed_at`.

### Get Output

```http
GET /v1/outputs/{id}
```

Returns output details.

### Publish Output

```http
POST /v1/outputs/{id}/publish
```

Publish output to a channel.

**Request Body:**
```json
{
  "channel": "twitter",
  "caption": "Check out this cosmic nebula!"
}
```

**Response:**
```json
{
  "published_url": "https://twitter.com/madfam/status/..."
}
```

---

## Error Responses

Errors are returned as FastAPI/JWT/Jose `detail` payloads (string or structured
object) plus standard HTTP status codes.

```json
{"detail": "Invalid credentials. Signal corrupted."}
```

```json
{
  "detail": {
    "message": "Template requires Pro or Studio access.",
    "required_entitlement": "paid_template"
  }
}
```

```json
{"detail": "Signal lost. Authentication required."}
```

Typical statuses are `400`, `401`, `403`, `404`, `409`, `413`, `422`, `429`, and
`500`, depending on the endpoint and error path.

---

## Rate Limits

Current limits are configured by middleware in `apps/api/src/ceq_api/middleware.py`
and `apps/api/src/ceq_api/routers/interest.py`:

- Default production request limit: `100/minute`.
- `/v1/interest/` has an explicit limiter of `10/hour`.
- Active job concurrency is controlled by `MAX_ACTIVE_JOBS_*` settings (`0` means
  no cap).

---

## SDKs

### Python

```python
from ceq import CEQClient

client = CEQClient(token="your-jwt-token")

# Run a workflow
job = client.workflows.run(
    workflow_id="uuid",
    params={"prompt": "cosmic nebula", "seed": 42}
)

# Wait for completion
result = job.wait()
print(result.output_urls)
```

### TypeScript

```typescript
import { CEQClient } from '@ceq/sdk';

const client = new CEQClient({ token: 'your-jwt-token' });

// Run a workflow
const job = await client.workflows.run({
  workflowId: 'uuid',
  params: { prompt: 'cosmic nebula', seed: 42 }
});

// Stream progress
for await (const update of job.stream()) {
  console.log(update.step, '/', update.totalSteps);
}

const result = await job.result();
console.log(result.outputUrls);
```

---

*For more details, see the [OpenAPI spec](/v1/openapi.json).*
