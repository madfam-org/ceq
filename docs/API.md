# CEQ API Reference

API documentation for CEQ — Creative Entropy Quantized.

**Base URL:** `https://api.ceq.lol`
**Authentication:** Bearer token (Janua JWT)

## Authentication

All API requests require a valid JWT token from Janua:

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
  "status": "healthy",
  "version": "0.1.0"
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
| `offset` | int | Pagination offset |
| `tag` | string | Filter by tag |

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
| `status` | string | Filter: queued, running, completed, failed |
| `limit` | int | Max results (default: 50) |
| `offset` | int | Pagination offset |

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
  "input_params": { "prompt": "...", "seed": 42 },
  "output_urls": [
    "https://ceq-assets.r2.cloudflarestorage.com/outputs/abc123.png"
  ],
  "execution_time_ms": 45000,
  "queued_at": "2025-12-10T12:00:00Z",
  "completed_at": "2025-12-10T12:02:30Z"
}
```

### Cancel Job

```http
DELETE /v1/jobs/{id}
```

Cancels a queued or running job.

**Response:** `204 No Content`

### Stream Job Updates (WebSocket)

```
WS /v1/jobs/{id}/stream
```

Real-time job progress updates.

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
      "output_type": "image",
      "storage_uri": "https://...",
      "thumbnail_uri": "https://...",
      "metadata": { "width": 1024, "height": 1024 },
      "created_at": "2025-12-10T12:00:00Z"
    }
  ]
}
```

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

All errors follow this format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input parameters",
    "details": {
      "prompt": "Required field"
    }
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `UNAUTHORIZED` | 401 | Invalid or missing token |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `VALIDATION_ERROR` | 422 | Invalid input |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Server error |

---

## Rate Limits

| Tier | Requests/minute | Concurrent jobs |
|------|-----------------|-----------------|
| Free | 60 | 2 |
| Pro | 300 | 10 |
| Enterprise | Unlimited | Unlimited |

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
