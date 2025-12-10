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
| `R2_BUCKET` | Yes | `ceq-assets` | R2 bucket name |

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

The API is deployed to Kubernetes via GitHub Actions. See [docs/PRODUCTION_DEPLOYMENT.md](../../docs/PRODUCTION_DEPLOYMENT.md).

```bash
# Check deployment
kubectl get pods -n ceq -l app=ceq-api

# View logs
kubectl logs -n ceq deployment/ceq-api

# Port forward for debugging
kubectl port-forward -n ceq deployment/ceq-api 5800:5800
```

## License

PROPRIETARY - MADFAM
