# CEQ evidence artifacts

Production verification outputs live here. Filenames use UTC timestamps:

```
YYYY-MM-DDTHHMMSSZ-<slug>.md
YYYY-MM-DDTHHMMSSZ-public-prod-endpoints.csv
```

## Capture commands

```bash
# Public endpoint matrix (no auth)
scripts/capture-public-endpoint-matrix.sh

# Public smoke only
CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh

# Full post-deploy bundle (copy ops/smoke-config.env.example first)
source ops/smoke-config.env
bash scripts/post-deploy-verify.sh --all
```

## Phase closure minimum

Each remediation phase should add one markdown file with:

1. UTC timestamp and operator
2. ArgoCD / git revision under test
3. Commands executed
4. HTTP status codes or job IDs
5. Output artifact URLs (R2) for GPU proofs
6. ExternalSecret readiness (`kubectl -n ceq get externalsecret`)

## Canonical template UUIDs (production)

| Template | UUID |
|----------|------|
| FLUX SCHNELL | `d8b30c7e-4501-493f-94c7-5223d7777afb` |
| FLUX.1 DEV | `94df20ca-280f-43a1-baa9-1c8b3f4eae48` |

See [`docs/CEQ_FULL_REMEDIATION_PLAN_2026-06-12.md`](../docs/CEQ_FULL_REMEDIATION_PLAN_2026-06-12.md).
