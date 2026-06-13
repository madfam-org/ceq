# CEQ live audit wrap-up — 2026-06-12

## Scope

Browser + API audit of production CEQ (`app.ceq.lol`, `api.ceq.lol`) with
`admin@madfam.io` credentials. Cross-referenced Tulana, internal-devops, and
solarpunk-foundry for GPU compute strategy.

## Findings

| Area | Status | Detail |
|------|--------|--------|
| Public edge | Green | `/health`, `/ready`, landing, Janua OAuth 302 |
| Studio login | Green | Session JWT with `aud: ceq-api`, `roles: ["admin"]` |
| Authenticated API | **Red** | 401 `"Invalid credentials. Signal corrupted."` — missing JWKS env on `ceq-api` |
| Template catalog | Green | 13 templates public; counts 4/3/3/3 by category |
| GPU workers | **Red** | `ceq-worker` 0 replicas; no orchestrator deployed |
| Billing | Yellow | Checkout disabled; credits unavailable |
| ExternalSecret | Yellow | `ceq-janua-client-secret` degraded if Vault gap persists |

## Repo remediations (Phases 0–4)

Documented in [`CEQ_FULL_REMEDIATION_PLAN_2026-06-12.md`](./CEQ_FULL_REMEDIATION_PLAN_2026-06-12.md):

- Phase 0: Janua JWT env vars + ExternalSecret manifests
- Phase 2: Studio `isApiAuthorized` probe + live template hub
- Phase 3: Vast orchestrator + `CEQ_WORKER_REDIS_URL` external connectivity
- Phase 4: `post-deploy-verify.sh`, smoke config, GitHub post-deploy workflow

## Operator next steps

1. Populate Vault secrets (`JANUA_CLIENT_SECRET`, `VAST_API_KEY`, `CEQ_WORKER_REDIS_URL`)
2. Merge remediation PR → ArgoCD sync
3. Run `bash scripts/post-deploy-verify.sh --all` with `CEQ_AUTH_TOKEN`
4. Capture evidence in `ops/evidence/`

## Related

- [`GPU_COMPUTE_STRATEGY.md`](./GPU_COMPUTE_STRATEGY.md)
- `internal-devops/decisions/2026-06-12-ceq-gpu-compute-provider-strategy.md`
