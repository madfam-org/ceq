# CEQ Docs Evidence Audit - 2026-06-02

This is a supplemental evidence snapshot focused on public production readiness after the latest merge window.

## Public production evidence updates

- `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh` result: [../ops/evidence/2026-06-02-live-public-smoke.md](../ops/evidence/2026-06-02-live-public-smoke.md)
- `capture-public-endpoint-matrix.sh` result: [../ops/evidence/2026-06-02-live-public-matrix.csv](../ops/evidence/2026-06-02-live-public-matrix.csv)
- `/v1/templates/` is non-empty in the latest public snapshot (sample IDs):
  - `94df20ca-280f-43a1-baa9-1c8b3f4eae48`
  - `d8b30c7e-4501-493f-94c7-5223d7777afb`
  - `25186ef2-6b16-4b74-9be1-a5c5037d82b4`

## Outstanding runtime blockers (unchanged)

- Authenticated `GET /v1/operations/status` with admin JWT is still required to complete P0.
- Authenticated production GPU golden path (`job -> callback -> output -> gallery`) is still required for Tier B/C readiness.
