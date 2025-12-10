# CEQ Task Completion Checklist

## Before Marking Task Complete

### TypeScript Changes (Studio)
```bash
# Type checking
pnpm --filter @ceq/studio typecheck

# Linting
pnpm --filter @ceq/studio lint

# Build verification
pnpm --filter @ceq/studio build
```

### Python Changes (API)
```bash
cd apps/api

# Linting
ruff check src/

# Formatting
ruff format src/ --check

# Type checking
mypy src/

# Tests (if applicable)
pytest
```

### Python Changes (Workers)
```bash
cd apps/workers

# Linting
ruff check src/

# Formatting
ruff format src/ --check

# Type checking
mypy src/
```

### Database Changes
```bash
cd apps/api

# Generate migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head

# Verify migration
alembic current
```

### All Changes
```bash
# Full project verification
pnpm typecheck
pnpm lint
pnpm build
```

## Quality Gates

1. ✅ All type checks pass
2. ✅ All linting passes  
3. ✅ Build succeeds
4. ✅ Tests pass (if modified)
5. ✅ No console errors in browser (studio)
6. ✅ API endpoints return expected responses
