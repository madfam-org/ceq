# CEQ Docs Evidence Audit - 2026-06-02

This is a supplemental evidence snapshot focused on public production readiness after the latest merge window.

Related: [`README.md`](./README.md), [`CEQ_CODEBASE_AUDIT_WRAPUP_2026-06-02.md`](./CEQ_CODEBASE_AUDIT_WRAPUP_2026-06-02.md), [`GA_DEMO_DEFINITION.md`](./GA_DEMO_DEFINITION.md), [`COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md).

## Public production evidence updates

- `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh` result: [../ops/evidence/2026-06-02-live-public-smoke.md](../ops/evidence/2026-06-02-live-public-smoke.md)
- `capture-public-endpoint-matrix.sh` result: [../ops/evidence/2026-06-02T041548Z-public-prod-endpoints.csv](../ops/evidence/2026-06-02T041548Z-public-prod-endpoints.csv)
- `2026-06-02T04:15Z` public smoke rerun passed locally.
- `2026-06-02T04:15Z` public endpoint matrix was captured at [../ops/evidence/2026-06-02T041548Z-public-prod-endpoints.csv](../ops/evidence/2026-06-02T041548Z-public-prod-endpoints.csv).
- `GET /ready` returned `200`; unauthenticated `GET /v1/credits/balance` returned `401`; unauthenticated `GET /v1/operations/status` returned `401`.
- `/v1/templates/` is non-empty in the latest public snapshot (sample IDs):
  - `94df20ca-280f-43a1-baa9-1c8b3f4eae48`
  - `d8b30c7e-4501-493f-94c7-5223d7777afb`
  - `25186ef2-6b16-4b74-9be1-a5c5037d82b4`

## Runtime evidence updates

- Enclii `ops.pods.diagnose` for `ceq-worker` returned `count: 0`; no worker pods were running during the 2026-06-02T04:15Z check.
- Read-only Kubernetes CRD inspection found `ceq-secrets` synced and `ceq-janua-client-secret` present as a Secret, but the `ceq-janua-client-secret` ExternalSecret is `SecretSyncedError` because Vault path `secret/ceq` is missing property `JANUA_CLIENT_SECRET`.
- Live Service label remediation was applied with read-only-safe scope plus a metadata patch: `service/ceq-api` now carries `app=ceq-api` so the committed `ServiceMonitor` selector can match it.
- Enclii currently exposes pod diagnosis, but this audit still needed read-only raw Kubernetes access for ExternalSecret/KEDA/ServiceMonitor/PrometheusRule state. Missing Enclii adapter gap: expose application secret-sync and autoscaler/monitoring CRD readiness through Enclii.

## Outstanding runtime blockers (unchanged)

- Authenticated `GET /v1/operations/status` with admin JWT is still required to complete P0.
- Authenticated production GPU golden path (`job -> callback -> output -> gallery`) is still required for Tier B/C readiness.
- Worker capacity must be available before the GPU golden path can be proven; zero `ceq-worker` pods were running in the latest Enclii check.

## Additional live ops evidence captured 2026-06-02T04:27Z

- `gh secret list --repo madfam-org/ceq` shows repo secret `JANUA_CLIENT_SECRET` exists by name, last updated `2026-05-23T07:39:45Z`.
- Triggered fallback GitHub workflow `sync-janua-client-secret.yml`; run `26798391929` completed `success` at `2026-06-02T04:27:50Z`. This refreshes live Kubernetes Secret `ceq-janua-client-secret` from the GitHub Actions secret, but does not populate Vault.
- Enclii `ops.secrets.external` for `ceq-janua-client-secret` reports `Ready=False`, reason `SecretSyncedError`, message `could not get secret data from provider`.
- Enclii `ops.secrets.refresh` dry-run is `ready_to_apply`, but the planned mutation is only a force-sync annotation. It is intentionally not applied because the provider still lacks `secret/ceq.JANUA_CLIENT_SECRET`, so refresh would be a no-op for readiness.
- Enclii `ops.apps.status ceq-services` reports Argo sync `Synced` at revision `f6487bf035c4868ada6576369f74cf6023bd30f4`, but health `Degraded` with the ExternalSecret as the material degraded resource.
- Enclii service-secret CLI cannot currently operate on CEQ because `enclii.yaml` is status-only and fails schema validation (`spec.build.type` missing). This is an Enclii onboarding/adapter gap for CEQ secret mutation.

## Additional platform readiness evidence captured 2026-06-02T04:30Z

- Enclii `ops.storage.pvc --namespace ceq` reports `count: 0`; CEQ has no live PVCs in namespace, so worker/model/cache storage is not provisioned as a live platform dependency.
- Enclii `ops.jobs.list --namespace ceq` reports `count: 0` CronJobs; recurring operational jobs are not part of the live CEQ namespace.
- Enclii `ops.pods.diagnose ceq-api --namespace ceq` reports 2 API pods `Running`, `Ready=True`, restart count `0`.
- Enclii `ops.policy.violations --namespace ceq` reports 40 policy report resources. Detailed read-only policy report summarization shows active failures are dominated by `require-probes/autogen-require-readiness-probe` (12 failed reports), plus `disallow-latest-tag/autogen-disallow-latest` and `require-image-digest/autogen-require-digest` on 2 reports each.
- Enclii `ops.policy.exceptions --namespace ceq` currently fails with `the server could not find the requested resource`; the policy adapter also does not expose result-level failure details. This is an Enclii policy adapter/reporting gap for actionable CEQ policy remediation.

## Additional Enclii observability evidence captured 2026-06-02T04:32Z

- Enclii cluster health filtered for CEQ returns `ceq-studio` service `c64c545a-0a60-4aea-a2be-8222a9d82b1d` healthy with `2/2` ready pods and `ceq-api` service `e290ef2d-1093-45f3-864a-b2a600fa48f1` healthy with `2/2` ready pods.
- Enclii service-specific metrics for both CEQ service IDs return default/empty telemetry (`captured_at 0001-01-01 00:00`, CPU/memory/RPS/latency all `0`).
- Enclii service-specific alerts for both CEQ service IDs return ten malformed critical rows with empty service/summary and timestamp `0001-01-01 00:00`. CEQ health registration exists, but metrics/alert telemetry is not actionable through Enclii today.

## Additional auth-token evidence captured 2026-06-02T04:34Z

- Local environment check found `CEQ_AUTH_TOKEN` and `CEQ_ADMIN_AUTH_TOKEN` absent.
- GitHub repo secret name scan for `CEQ|AUTH|TOKEN|JANUA` returns only `JANUA_CLIENT_SECRET`; no CEQ smoke/admin auth token is available by name through repo secrets.
- Authenticated operations smoke and render/golden-path proof remain blocked on a real CEQ user/admin token or browser-login token capture.
