# CEQ Docs Evidence Audit - 2026-06-01

This audit cross-checks CEQ documentation against the repository and public
production endpoints. It does not use raw cluster access or real Janua user
credentials.

## Public Production Evidence

| Check | Result | Evidence |
|-------|--------|----------|
| `endpoint matrix generator` | executable | `scripts/capture-public-endpoint-matrix.sh` |
| `2026-06-01 public smoke` | pass | [`CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh`](../ops/evidence/2026-06-01-public-prod-smoke.md) |
| `2026-06-01 unauth endpoint matrix` | **stale** (attempted) | Endpoint matrix probe was DNS/connectivity-failing during this attempt; last successful snapshot is `../ops/evidence/2026-06-01b-prod-endpoints.csv` |
| `https://api.ceq.lol/health` | 200 JSON | `{"status":"ok","service":"ceq-api","version":"0.1.0"}` |
| `https://api.ceq.lol/ready` | 200 JSON | `status: ready`, `database: ok`, `redis: ok` |
| `https://ceq.lol/` | 200 | Public landing reachable |
| `https://app.ceq.lol/` without cookies | 307 | Redirects to `https://app.ceq.lol/login?returnTo=%2F` |
| `https://app.ceq.lol/login` | 200 | Login surface reachable |
| `https://api.ceq.lol/docs` | 404 | OpenAPI disabled in production |
| `GET /v1/jobs` | 307 | Redirects to `/v1/jobs/` in this deployment |
| unauthenticated `GET /v1/templates/` | 200 JSON | `{ "templates": [], "total": 0, "skip": 0, "limit": 50 }` (catalog appears unseeded in this public check) |
| `unauthenticated GET /v1/jobs/` | 401 | `{"detail":"Signal lost. Authentication required."}` |
| unauthenticated `POST /v1/render/card` | 401 | Render API is auth-gated in prod |
| unauthenticated `GET /v1/credits/balance` | 404 | Credits API is not currently routable in production |
| Janua authorize for CEQ client | 302 | Redirects to Janua login, client name `ceq-studio` |
| `https://app.ceq.lol/api/auth/session` without cookies | 401 | Session endpoint correctly rejects no-cookie requests |
| `POST /api/auth/token` with bogus code | 400 `invalid_grant` | Janua accepts the client secret; code is invalid as expected |
| `https://auth.madfam.io/logout?...` | 404 | Logout route remains a Janua P1 follow-up |
| `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh` | pass | API health, host split, and app auth-gate checks pass |
| GitHub branch protection on `main` | enabled | Requires six CEQ CI checks, one review, stale-review dismissal, admin enforcement, conversation resolution; force-push/delete disabled |

## Repository Evidence

| Claim | Source evidence |
|-------|-----------------|
| Main branch protection is active and enforces 6 CEQ checks plus PR safeguards | `gh api repos/madfam-org/ceq/branches/main/protection` (2026-06-01)
| API runs on port 5800 | `apps/api/src/ceq_api/config.py`, `infrastructure/k8s/api-deployment.yaml` |
| Studio runs on port 5801 | `infrastructure/k8s/studio-deployment.yaml` |
| Services are digest-pinned in GitOps | `infrastructure/k8s/kustomization.yaml` |
| OpenAPI disabled in prod | `apps/api/src/ceq_api/main.py` sets docs URLs only when not production |
| Render templates are `card-standard`, `tone-beep`, `card-plate` | `apps/api/src/ceq_api/render/renderers/__init__.py` |
| Render hash is deterministic sorted JSON + SHA-256 | `apps/api/src/ceq_api/render/hash.py` |
| Render cache key shape is `render/{template}/{hash}.{ext}` | `apps/api/src/ceq_api/render/cache.py` |
| Render endpoints require Janua auth | `apps/api/src/ceq_api/routers/render.py` dependencies |
| Worker callback token is required in production | `apps/api/src/ceq_api/config.py` validation |
| Completion dead-letter operations exist | `apps/api/src/ceq_api/routers/operations.py` |
| Active cancellation uses Redis state + control channel | `apps/api/src/ceq_api/routers/jobs.py`, `apps/workers/src/ceq_worker/queue.py` |
| Seed catalog has 13 DB templates | `apps/api/src/ceq_api/seed_templates.py` |
| Checked-in workflow files total 6 | `templates/` |
| Studio token exchange uses server-side `JANUA_CLIENT_SECRET` | `apps/studio/src/app/api/auth/token/route.ts` |
| Studio manifest reads `JANUA_CLIENT_SECRET` from `ceq-janua-client-secret` | `infrastructure/k8s/studio-deployment.yaml` |
| Credit ledger and metering primitives exist in code | `apps/api/src/ceq_api/models/credit.py`, `credit_ledger.py`, `job_billing.py` |
| Plan-aware active-job caps exist | `apps/api/src/ceq_api/quotas.py` |

## Corrections Made

| Area | Correction |
|------|------------|
| Janua status | Updated docs from "Vault sync pending" to "token route accepts client secret; browser proof pending" where supported by live evidence. |
| Secret wiring | Added `ceq-janua-client-secret` ExternalSecret and aligned docs to the dedicated Secret used by Studio. |
| Ingress | Added `app.ceq.lol` to the committed ingress host/TLS list to match documented and live host split. |
| Render auth | Removed claims that `/v1/render/*` is public/free-open; it is stable but Janua-authenticated in prod. |
| API docs | Corrected health response and added render endpoint reference. |
| Template docs | Replaced placeholder template catalog with the actual checked-in files, 13 DB seed templates, and render templates. |
| Template catalog in prod | Added verification row for `GET /v1/templates/`; production currently returns an empty list, indicating seeding needs re-check. |
| Deployment docs | Replaced stale `ceq-prod` tunnel guidance with platform `enclii-prod` tunnel status. |
| Legacy deploy script | Disabled legacy `ceq-prod` tunnel creation unless `CEQ_ALLOW_LEGACY_TUNNEL=true` is explicitly set. |
| Digest docs | Updated current kustomization digest table in the stability roadmap. |
| Commercial controls | Added credit ledger, role-derived entitlement/quota guards, feature-flagged render/GPU debits, and Studio balance readout to docs. |
| Branch protection | Enabled `main` protection and removed it from open GA blockers. |

## Remaining Unverified Claims

These require credentials, admin access, or cluster access and were not proven by
this public audit:

| Claim | Required proof |
|-------|----------------|
| Real browser login completes and lands in Studio shell | Operator login with real Janua credentials |
| `GET /api/auth/session` returns user + access token after login | Browser session cookies from a real login |
| `GET /v1/credits/balance` with authenticated user | Valid Janua JWT and deployed credits route |
| `GET /v1/operations/status` is green | Admin Janua JWT |
| Alembic head is applied in production DB | Admin operations status or DB/ArgoCD access |
| Worker pods or Vast.ai workers are healthy | Enclii workload status or provider dashboard |
| GPU job reaches R2, callback, PostgreSQL, and gallery | Authenticated production smoke with seeded template UUID |
| Alert routing reaches on-call | Enclii observability tenant access |

## Current Conclusion

CEQ public edge, host split, API health, production OpenAPI posture, Janua client
registration, and Studio token-route secret wiring are evidence-backed. Full
Tier B / GA-demo readiness still depends on real browser login proof, runtime
operations-status proof, a confirmed production credits API surface, and at least
one authenticated GPU golden-path smoke.
