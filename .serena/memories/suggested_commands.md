# CEQ Suggested Commands

## Development

```bash
# Install dependencies
pnpm install

# Run all services (via turbo)
pnpm dev

# Run studio only (port 5801)
pnpm dev:studio
# or: pnpm --filter @ceq/studio dev

# Run API only (port 5800)
pnpm dev:api
# or: cd apps/api && ./venv/bin/uvicorn ceq_api.main:app --reload --host 0.0.0.0 --port 5800

# Run worker (requires GPU)
pnpm dev:worker
# or: cd apps/workers && python -m ceq_worker.queue
```

## Build & Quality

```bash
# Build all
pnpm build

# Type check all
pnpm typecheck

# Lint all
pnpm lint

# Test all
pnpm test

# Clean all
pnpm clean
```

## Python (API/Workers)

```bash
# Navigate to API
cd apps/api

# Activate virtual environment
source .venv/bin/activate

# Run ruff linting
ruff check src/

# Run ruff formatting
ruff format src/

# Run mypy type checking
mypy src/

# Run pytest
pytest

# Alembic migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

## Workers Specific

```bash
cd apps/workers

# Run worker queue
python -m ceq_worker.queue

# Run orchestrator
python -m ceq_worker.orchestrator
```

## Utility

```bash
# Turbo commands
turbo run dev --filter=@ceq/studio
turbo run build --filter=@ceq/api
turbo run typecheck

# Docker
docker build -t ceq-api apps/api
docker build -t ceq-studio apps/studio
docker build -t ceq-worker apps/workers
```
