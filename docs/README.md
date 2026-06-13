# CEQ documentation map

This is the navigation and truth layer for CEQ documentation. Use it before
trusting older roadmap, handoff, or deployment notes.

## Current truth sources

| Document | Use it for |
|---|---|
| [`CEQ_FULL_REMEDIATION_PLAN_2026-06-12.md`](./CEQ_FULL_REMEDIATION_PLAN_2026-06-12.md) | **Active** phased remediation plan (identity → GPU → strict smoke → commercial GA) |
| [`CEQ_CODEBASE_AUDIT_WRAPUP_2026-06-02.md`](./CEQ_CODEBASE_AUDIT_WRAPUP_2026-06-02.md) | Audit summary, remediations, live blockers, and recommended ROI order |
| [`DOCS_EVIDENCE_AUDIT_2026-06-02.md`](./DOCS_EVIDENCE_AUDIT_2026-06-02.md) | Evidence-backed production facts from public smoke, Enclii, GitHub, Kubernetes, policy, and observability checks |
| [`GA_DEMO_DEFINITION.md`](./GA_DEMO_DEFINITION.md) | Capped GA demo scope and proof requirements |
| [`COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md) | Commercial GA gates and paid-launch remediation plan |
| [`COMMERCIAL_LAUNCH_READINESS_PACK.md`](./COMMERCIAL_LAUNCH_READINESS_PACK.md) | Paid-launch evidence pack, support checklist, legal/commercial readiness |

## Current status in one paragraph

CEQ has live public surfaces and passing public no-auth smoke. `ceq-api` and
`ceq-studio` are healthy in Enclii health at 2/2 ready pods, and `/ready`
returns 200. A **2026-06-12 live audit** confirmed authenticated API routes
return 401 because production `ceq-api` lacks Janua JWKS/issuer/audience env
vars — repo fixes are ready in Phase 0 of
[`CEQ_FULL_REMEDIATION_PLAN_2026-06-12.md`](./CEQ_FULL_REMEDIATION_PLAN_2026-06-12.md).
CEQ is not commercial GA: Vault may still be missing secrets, GPU golden-path
proof is not captured, Enclii metrics/alerts are not actionable, and
billing/entitlements are not paid-launch proven.

## Documentation precedence

When documents conflict, prefer this order:

1. Latest evidence audit, currently [`DOCS_EVIDENCE_AUDIT_2026-06-02.md`](./DOCS_EVIDENCE_AUDIT_2026-06-02.md).
2. Latest wrap-up, currently [`CEQ_CODEBASE_AUDIT_WRAPUP_2026-06-02.md`](./CEQ_CODEBASE_AUDIT_WRAPUP_2026-06-02.md).
3. Active plans: [`GA_DEMO_DEFINITION.md`](./GA_DEMO_DEFINITION.md), [`COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md), [`CEQ_STABILITY_ROADMAP.md`](./CEQ_STABILITY_ROADMAP.md).
4. Operator and handoff docs, which may include historical context.
5. Legacy embedded sections in [`AGENTS.md`](../AGENTS.md), [`ECOSYSTEM.md`](../ECOSYSTEM.md), and older session wrap-ups.

## Product and launch docs

| Document | Role |
|---|---|
| [`GA_DEMO_DEFINITION.md`](./GA_DEMO_DEFINITION.md) | Defines Tier A/B/C demo scope and acceptance gates |
| [`COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md) | Tracks the work needed to sell, meter, support, and operate CEQ commercially |
| [`COMMERCIAL_LAUNCH_READINESS_PACK.md`](./COMMERCIAL_LAUNCH_READINESS_PACK.md) | Collects evidence, support, legal, and alert-readiness launch artifacts |
| [`PRD.md`](./PRD.md) | Product requirements and broader ambition |
| [`LANDING_CONVERSION_AUDIT_2026-06-02.md`](./LANDING_CONVERSION_AUDIT_2026-06-02.md) | Landing-page conversion findings |

## Operations and identity docs

| Document | Role |
|---|---|
| [`JANUA_OPERATOR.md`](./JANUA_OPERATOR.md) | CEQ-side Janua operator checklist and current identity blockers |
| [`JANUA_AGENT_HANDOFF.md`](./JANUA_AGENT_HANDOFF.md) | Janua-side handoff and OAuth coordination notes |
| [`PLATFORM_AGENT_HANDOFFS.md`](./PLATFORM_AGENT_HANDOFFS.md) | Platform/Vault/Kubernetes/acceptance handoff prompts and known adapter gaps |
| [`PRODUCTION_DEPLOYMENT.md`](./PRODUCTION_DEPLOYMENT.md) | Production deployment guide; contains legacy raw commands and must be read Enclii-first |
| [`CEQ_STABILITY_ROADMAP.md`](./CEQ_STABILITY_ROADMAP.md) | Stability roadmap, smoke matrix, critical path, and historical closure record |

## Developer docs

| Document | Role |
|---|---|
| [`GETTING_STARTED.md`](./GETTING_STARTED.md) | Product and developer quick start |
| [`API.md`](./API.md) | API reference |
| [`TEMPLATES.md`](./TEMPLATES.md) | Template catalog and render API notes |
| [`VAST_AI_SETUP.md`](./VAST_AI_SETUP.md) | Vast.ai GPU provider operator runbook |
| [`GPU_COMPUTE_STRATEGY.md`](./GPU_COMPUTE_STRATEGY.md) | Ecosystem-aligned compute provider strategy (Vast → Furnace) |

## Evidence artifacts

Evidence files live under [`../ops/evidence`](../ops/evidence). The most recent
public production evidence from the 2026-06-02 audit includes:

- [`../ops/evidence/2026-06-02-live-public-smoke.md`](../ops/evidence/2026-06-02-live-public-smoke.md)
- [`../ops/evidence/2026-06-02T041548Z-public-prod-endpoints.csv`](../ops/evidence/2026-06-02T041548Z-public-prod-endpoints.csv)

## Claim hygiene rules

- Do not mark CEQ commercial GA until billing, entitlements, quotas, support,
  alerting, and authenticated render proof are captured.
- Do not treat a present Kubernetes Secret as a healthy ExternalSecret; verify
  the ExternalSecret condition and Vault source.
- Do not treat public smoke as authenticated smoke.
- Do not treat mocked Janua Playwright tests as live browser-login proof.
- Do not treat a deployed worker manifest as worker capacity; verify live worker
  pods and a successful job path.
- When raw infrastructure access is used because Enclii lacks an adapter, record
  the adapter gap in the relevant evidence doc.
