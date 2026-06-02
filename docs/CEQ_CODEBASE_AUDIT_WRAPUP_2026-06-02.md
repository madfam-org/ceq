# CEQ codebase audit wrap-up - 2026-06-02

## Scope

This wrap-up records the codebase ingestion, live production evidence, remediations,
and remaining gaps from the 2026-06-02 CEQ audit.

Primary evidence file:

- `docs/DOCS_EVIDENCE_AUDIT_2026-06-02.md`

Generated production evidence:

- `ops/evidence/2026-06-02-live-public-smoke.md`
- `ops/evidence/2026-06-02T040106Z-public-prod-endpoints.csv`
- `ops/evidence/2026-06-02T041548Z-public-prod-endpoints.csv`

## Actions completed

- Ran public production smoke. Public API, landing, studio gate, and login handoff
  checks passed.
- Captured public endpoint matrix evidence.
- Refreshed the fallback GitHub Actions sync for `JANUA_CLIENT_SECRET`; run
  `26798391929` completed successfully at `2026-06-02T04:27:50Z`.
- Applied live label `app=ceq-api` to the production `ceq-api` Service so the
  ServiceMonitor selector can match.
- Updated source manifest for the same Service label so GitOps can preserve it.
- Added alert runbook URLs to CEQ PrometheusRule annotations.
- Removed the unsafe Studio Docker build fallback from frozen-lockfile install.
- Recorded Enclii, GitHub, Kubernetes, policy, storage, pod, and observability
  evidence in the audit doc.

## Current production posture

- Public CEQ surfaces are up from a no-auth perspective.
- `ceq-api` and `ceq-studio` are healthy in Enclii health with `2/2` ready pods.
- API `/ready` returns `200`.
- Unauthenticated protected endpoints correctly return `401`.
- `ceq-services` is Argo `Synced`.
- `ceq-services` health is still `Degraded` because `ceq-janua-client-secret`
  ExternalSecret is not ready.

## Remaining P0 gaps

- Vault path `secret/ceq` is missing property `JANUA_CLIENT_SECRET`; ExternalSecret
  `ceq-janua-client-secret` remains `SecretSyncedError`.
- Authenticated production smoke is blocked because local `CEQ_AUTH_TOKEN` and
  `CEQ_ADMIN_AUTH_TOKEN` are absent, and GitHub repo secrets do not expose a CEQ
  smoke/admin token by name.
- GPU/render golden path is not proven. `ceq-worker` has `0/0` live pods, KEDA is
  inactive, and CEQ has no live PVCs in Enclii storage inspection.
- Enclii metrics and alerts for CEQ are not actionable: service metrics return
  default zero snapshots and alert reads return malformed critical rows.
- Kyverno reports show unresolved policy failures, primarily missing readiness
  probes, plus latest-tag/digest immutability failures on two reports.
- CEQ Enclii service spec is status-only; `enclii secrets` cannot operate against
  it because required build metadata is absent.

## Enclii adapter gaps recorded

- CEQ secret mutation is not currently available through the service secret CLI
  because `enclii.yaml` is not a full service spec.
- Enclii policy violation reads expose report names but not enough result-level
  detail for direct remediation.
- Enclii policy exceptions endpoint is unsupported in the current cluster/API path.
- Enclii CEQ metrics and alert reads return placeholder/default data rather than
  operational telemetry.

## Recommended next ROI order

1. Populate Vault `secret/ceq.JANUA_CLIENT_SECRET` through the proper Selva or
   Enclii operator path, then verify ExternalSecret readiness.
2. Obtain a real CEQ user/admin token or browser-login token capture and run strict
   authenticated production smoke.
3. Prove the render golden path end-to-end with worker capacity, queue processing,
   and persisted artifact URL.
4. Repair CEQ observability ingestion for metrics and alerts.
5. Remediate policy report failures and improve Enclii policy adapter detail.
6. Fully onboard CEQ into Enclii service spec support so secrets and operational
   workflows no longer require break-glass paths.

## Notes

- No full local test suite was run during this wrap-up.
- Production raw Kubernetes usage was limited to targeted read-only evidence and
  one narrow Service label remediation because the Enclii-first adapter path lacked
  the necessary mutation/detail surface for those checks.
