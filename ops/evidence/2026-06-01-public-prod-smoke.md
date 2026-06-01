# CEQ Production Evidence — Public Surface (2026-06-01)

- Date: 2026-06-01
- Operator: local automation run
- Evidence command: `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh`
- Host/edge behavior in this session: DNS/network intermittency observed on repeated direct endpoint probing.

## Public smoke result

- **Result:** PASS
- Checks executed: API health, landing host response, host split, and app auth-gate redirect.

### Smoke output checks

- `https://api.ceq.lol/health`: response contains `status`.
- `https://ceq.lol`: HTTP 200
- `https://app.ceq.lol/` (no session): HTTP 307 to `/login?returnTo=%2F`
- `https://app.ceq.lol/login`: reachable

### Evidence matrix note

The full unauthenticated endpoint matrix from this session did **not** resolve
consistently and is treated as **stale**:

- `ops/evidence/2026-06-01-public-prod-endpoints.csv` (latest attempted run, not green)

For the latest fully successful endpoint snapshot, use:

- `ops/evidence/2026-06-01b-prod-endpoints.csv`

`2026-06-01b-prod-endpoints.csv` includes:

- `https://api.ceq.lol/health`
- `https://api.ceq.lol/ready`
- `https://api.ceq.lol/docs`
- `https://api.ceq.lol/v1/jobs` → trailing-slash redirect
- `https://api.ceq.lol/v1/jobs/` → auth-required
- `https://api.ceq.lol/v1/operations/status` → auth-required
- `https://app.ceq.lol/` → auth gate
- `https://app.ceq.lol/login`
- `https://app.ceq.lol/api/auth/session`
