# CEQ Commercial GA Remediation and Implementation Plan

> **Last updated:** 2026-06-01
> **Audience:** Product, engineering, platform, operators, support
> **Status:** Planning baseline. CEQ is not commercially GA yet.
> **Related:** [`DOCS_EVIDENCE_AUDIT_2026-06-01.md`](./DOCS_EVIDENCE_AUDIT_2026-06-01.md), [`CEQ_STABILITY_ROADMAP.md`](./CEQ_STABILITY_ROADMAP.md), [`GA_DEMO_DEFINITION.md`](./GA_DEMO_DEFINITION.md), [`COMMERCIAL_LAUNCH_READINESS_PACK.md`](./COMMERCIAL_LAUNCH_READINESS_PACK.md)

---

## Executive Summary

CEQ can support a technical demo today and is on track for a capped GA demo once
browser login, runtime secrets, and one authenticated GPU golden path are proven.
That is not the same as commercial GA.

**Commercial GA distance:** approximately **48%** as of this audit.

- Technical demo and infrastructure readiness: ~100% (live evidence)
- Capped GA readiness: ~68%
- Full stability: ~55%
- Limited commercial pilot: ~50%
- Commercial GA: ~45%

The score is evidence-weighted against the checklist in this document, not a
marketing estimate.

**Commercial GA means CEQ can be sold, onboarded, metered, supported, and
operated for paying users without manual exceptions.** The remaining gap is
mostly productization and operations: billing/credits, entitlement enforcement,
quota and abuse controls, support readiness, alert routing, and repeatable GPU
capacity proof.

Planning readiness as of 2026-06-01:

| Milestone | Planning readiness | Basis |
|-----------|--------------------|-------|
| Public technical demo | Ready now | Public smoke green; landing/API live |
| Capped GA demo | ~55-65% | Identity token route and browser login proof are now green; seeded-catalog and GPU proof remain open |
| Full stability | ~50-60% | Core runtime is implemented; strict prod smoke still open |
| Limited commercial pilot | ~50-60% | Credit/entitlement/queue/metering primitives landed; needs funded balances, GPU proof, and one supportable cohort |
| Commercial GA | ~45-55% | Needs Dhanam billing, prod GPU proof, alert/support/legal launch pack |

These percentages are planning estimates, not automated measurements. Evidence
sources are the 2026-06-01 prod audit, `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh`,
local test matrix, and current code/docs state. The latest fully successful
unauthenticated endpoint matrix snapshot is `ops/evidence/2026-06-01b-prod-endpoints.csv`;
the latest endpoint-attempt run is stale in
`ops/evidence/2026-06-01-public-prod-endpoints.csv`.

### Evidence-weighted GA Score (2026-06-01)

| GA scope | Weight | Evidence status | Latest evidence |
|----------|--------|----------------|----------------|
| Capped GA demo | 30% | 52% | Browser login proof is now captured in production; operations/authenticated GPU path remains unproven in prod. |
| Full stability | 25% | 52% | Public smoke is green; alert/rollback drill + strict CI gate still pending. |
| Limited commercial pilot | 25% | 40% | Credits API + billing source exist, but route has no confirmed live auth flow and entitlements are role-derived. |
| Commercial GA | 20% | 43% | Product/legal/operations launch controls are drafted, not yet fully proven in production. |

Estimated aggregate readiness remains **48%** (evidence-weighted). This is a
single-source readiness value, not a prediction of time to GA.

### GA-Critical Execution Register (as-of 2026-06-01)

Use this registry as the canonical closure board for GA-blocking work.

| Priority | Action | Owner | Status | Completion signal |
|----------|--------|-------|--------|------------------|
| P0-1 | Capture real browser login proof on `app.ceq.lol` with authenticated session bootstrap (`/api/auth/session`, httpOnly cookies, Studio shell load). | Studio + Janua operator | **Complete** | `2026-06-01`: `GET /api/auth/session` returned `user`, `roles`, and `access_token` for `admin@madfam.io`; `ceq_access_token` + `ceq_refresh_token` cookies were present and `httpOnly`; Studio shell route was loaded. |
| P0-2 | Run `GET /v1/operations/status` with admin JWT and capture callback/webhook/migration/dead-letter readiness. | Platform + API | **In progress** | PR #38 updates Janua introspection to probe `/api/v1/oauth/userinfo` (with `/api/v1/auth/me` fallback) and normalize user id/roles payloads. Awaiting deploy + prod green capture. |
| P0-3 | Seed and verify non-empty `/v1/templates/` in production; record stable template UUIDs for smoke runs. | Platform + API | **Inconsistent** (`/v1/templates/` returns empty in public evidence run) | `docs/DOCS_EVIDENCE_AUDIT_2026-06-01.md` |
| P0-4 | Run authenticated GPU golden path smoke (`job → callback → output → gallery`) and capture output URL trail. | API + Workers + Platform | **Not started** | Not yet captured |
| P0-5 | Run active cancellation + multi-modal smoke under `CEQ_STRICT_SMOKE=true` with dead-letter threshold checks. | API + Workers | **Not started** | Not yet captured |
| P1-1 | Finalize Dhanam-backed plan/checkout path for paid signup and plan changes. | Product + Dhanam + API | **Not started** | Not yet captured |
| P1-2 | Replace role-derived paid API gates with entitlement checks backed by plan state and server-side grants. | API | **In progress** (role-based guards landed) | No plan-backed enforcement evidence yet |
| P1-3 | Enable and reconcile feature-flagged render/GPU debit-refund flow for a pilot cohort. | API | **In progress** (code paths exist, flags available) | Not yet bound to funded flow |
| P1-4 | Replace role-derived caps with plan/rate/spend quotas tied to production entitlements. | API + Platform | **In progress** (schema + quotas exist, billing source missing) | No paid traffic evidence |
| P1-5 | Confirm alert + rollback drill evidence, link synthetic alert path, and attach runbooks to alert annotations. | Platform + Support | **Not started** | Not yet linked |
| P1-6 | Publish and link customer-facing legal/commercial docs (terms, privacy, AUP, pricing, limits) from GA flows. | Product + Legal | **Not started** | Pending docs exposure |
| P1-7 | Publish fresh-account paid pilot rehearsal evidence (login, generation, invoice/receipt, output retrieval). | Product + Eng + Support | **Not started** | Not yet executed |
| P2 | Reconcile roadmap/docs truth after each phase closure and archive evidence row IDs centrally. | Repo docs owners | **In progress** | `COMMERCIAL_GA_REMEDIATION_PLAN.md`, `docs/DOCS_EVIDENCE_AUDIT_2026-06-01.md` |

### GA-closure lanes (ROI order)

Track completion with these five high-impact lanes before broader closure.

| Lane | Action item | Completion status |
|------|-------------|------------------|
| P0-1 | Get one full browser proof (`app.ceq.lol` session bootstrap + `/api/auth/session` user payload). | `Complete` (2026-06-01) |
| P0-2 | Capture green `GET /v1/operations/status` with admin JWT (`callback`, `webhook`, `revision`, `dead-letter`). | `In progress` |
| P0-3 | Restore non-empty seeded `/v1/templates/` and freeze canonical template IDs for smoke. | `Inconsistent` (public evidence still empty) |
| P0-4 | Prove authenticated GPU production golden path (`job → callback → output → gallery`) including one cancellation check. | `Not started` |
| P1-1 | Publish/verify credits balance + entitlement proof for paying cohort; attach paid pilot receipt/invoice evidence. | `In progress` |

No lane is marked complete until evidence is captured, reproducible, and linked from
`docs/DOCS_EVIDENCE_AUDIT_2026-06-01.md`.

---

## Commercial GA Definition

CEQ is commercially GA only when all categories below are true:

| Category | GA bar |
|----------|--------|
| Identity | Janua login, logout, session refresh, and account recovery are proven in production |
| Product scope | Supported workflows, templates, limits, and pricing are frozen and documented |
| Runtime | Authenticated GPU jobs complete reliably and persist outputs to R2/PostgreSQL |
| Billing | Dhanam-backed plan selection, checkout, invoicing/receipts, and failure handling are live |
| Credits | Usage metering and credit consumption are server-side, idempotent, and auditable |
| Entitlements | Free/pro/studio access is enforced by the API, not only by Studio UI overlays |
| Quotas | Per-user and per-plan rate limits, queue limits, spend caps, and abuse controls are live |
| Reliability | Alerts route to on-call; rollback/runbooks exist; strict smokes gate releases |
| Security | AuthZ boundaries, audit logs, secret hygiene, and public docs exposure are verified |
| Support | Onboarding, escalation, refund/credit adjustment, and incident comms are ready |
| Legal/commercial | Terms, privacy, acceptable-use, pricing, and customer-facing limits are published |

No "commercial GA" declaration should be made until these gates have concrete
evidence attached in this document or linked runbooks.

---

## Current Evidence Baseline

Re-verified 2026-06-01:

| Surface | Evidence |
|---------|----------|
| Public landing | `https://ceq.lol` returns HTTP 200 |
| API health | `https://api.ceq.lol/health` returns `status: ok` |
| API readiness | `https://api.ceq.lol/ready` reports database and Redis ok |
| Studio auth gate | `https://app.ceq.lol/` redirects unauthenticated users to login |
| Studio login page | `https://app.ceq.lol/login` returns HTTP 200 |
| OpenAPI exposure | `https://api.ceq.lol/docs` returns 404 in production |
| Jobs API redirect contract | `https://api.ceq.lol/v1/jobs` returns 307 to `/v1/jobs/` |
| Jobs auth | `GET /v1/jobs/` returns 401 without auth |
| Render auth | Unauthenticated `POST /v1/render/card` returns 401 |
| Janua client | Authorization request returns 302 for the documented client |
| Studio client secret | Bogus token code returns `invalid_grant`, not `invalid_client` |
| Public smoke | `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh` passes |
| Branch protection | `main` requires six CEQ CI checks, one review, stale-review dismissal, admin enforcement, and conversation resolution |
| Template catalog (`/v1/templates/`) | Returns empty in public check (`{"templates": [], "total": 0}`) |
| Production credits route | `GET /v1/credits/balance` returns 404 when unauthenticated |

### Evidence-backed GA blockers

| Blocker | Severity | Why it matters |
|---------|----------|----------------|
| Real operator browser proof on `app.ceq.lol` | ✅ **Cleared** | Commercial product acceptance can proceed to runtime secrets and GPU proof |
| `GET /v1/operations/status` (admin) | P0 | Proves runtime callbacks/webhook readiness and migration state |
| Authenticated GPU golden path in prod | P0 | Confirms core fulfillment before paid use |
| Template catalog seeded in prod | P1 | Workflow demo paths cannot run if `/v1/templates/` is empty |
| Dhanam plan/checkout path | P1 | Required for non-experimental paid conversion |
| Alert routing + on-call drill | P1 | Required for paid operations confidence |

Open evidence gaps:

| Gap | Blocks |
|-----|--------|
| `operations/status` proof for callback/webhook secrets | P0 | Runtime callback/webhook readiness remains required |
| `operations/status` still returning `401 Invalid credentials. Signal corrupted.` for `admin@madfam.io` session token | GPU acceptance, on-call confidence |
| Authenticated GPU golden path in prod | Demo, pilot, commercial fulfillment |
| Template catalog remains unseeded in prod (`/v1/templates/` returns empty) | Workflow demo and premium template path availability |
| Dhanam plan funding and entitlement source | Limited commercial pilot and commercial GA |
| Alert receiver/on-call proof | Full stability and commercial GA |

Code progress since this baseline:

| Date | Progress | Remaining |
|------|----------|-----------|
| 2026-06-01 | API-side premium template guard added for `pro`/`premium` tags across template fork/run, synthesis template selection, and premium-origin workflow runs | Replace role-only paid access with Dhanam-backed plan/entitlement source |
| 2026-06-01 | Credit ledger model/table/API added: user balance, user ledger, admin idempotent grants | Meter billable render/GPU paths with debit/refund entries and reconcile to billing |
| 2026-06-01 | Per-user active job cap added for workflow/template/synthesis submissions via `MAX_ACTIVE_JOBS_PER_USER` | Replace the global cap with plan-aware Dhanam quotas and Studio limit UI |
| 2026-06-01 | Studio credit balance UI is wired to `/v1/credits/balance` | Confirm endpoint is live in production and add usage history, upgrade, exhausted-credit, and payment-failure states |
| 2026-06-01 | Render cache-miss debit plumbing added behind `RENDER_CREDIT_DEBITS_ENABLED` | Fund balances from Dhanam/pilot grants, enable for pilot cohort, and add GPU job debit/refund metering |
| 2026-06-01 | Plan-aware active-job caps added for free/pro/studio/admin roles | Replace role-derived limits with Dhanam plan state when billing source is live |
| 2026-06-01 | GPU job debit/refund plumbing added behind `GPU_JOB_CREDIT_DEBITS_ENABLED` | Fund balances, enable for pilot cohort, and reconcile ledger to completed jobs/billing export |
| 2026-06-01 | GitHub `main` branch protection enabled with required CEQ CI checks and review gate | Keep required checks current as workflow names change |

---

## Release Ladder

### Tier A - Technical Demo

**Status:** Available now.

Scope:

- Public landing/API evidence
- Auth-gated render API contract
- `@ceq/sdk` consumer story
- No live Studio walkthrough required

Exit evidence:

```bash
CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh
```

### Tier B - Capped GA Demo

**Status:** Not declared ready.

Scope:

- Real Janua login on `app.ceq.lol`
- One golden authenticated GPU job
- R2 output visible in gallery
- Render pillar smoke with JWT
- InterestGate shown as demand capture, not paywall

Exit evidence:

```bash
CEQ_RUN_OPERATIONS_STATUS=true \
CEQ_REQUIRE_OPERATIONS_STATUS=true \
CEQ_AUTH_TOKEN=<janua-jwt> \
CEQ_ADMIN_AUTH_TOKEN=<admin-jwt> \
CEQ_TEMPLATE_ID=<seeded-image-template-uuid> \
scripts/production-smoke.sh
```

### Tier C - Full Stability

**Status:** Not declared ready.

Scope:

- Tier B plus cancel smoke
- Multi-modal template smokes
- Alert routing and runbooks
- Branch protection
- Strict release gate

Exit evidence:

```bash
CEQ_STRICT_SMOKE=true \
CEQ_AUTH_TOKEN=<janua-jwt> \
CEQ_ADMIN_AUTH_TOKEN=<admin-jwt> \
CEQ_TEMPLATE_ID=<image-template-uuid> \
CEQ_CANCEL_TEMPLATE_ID=<long-running-template-uuid> \
CEQ_TEMPLATE_SMOKES_JSON='[...]' \
CEQ_EXPECT_MAX_COMPLETION_DEAD_LETTERS=0 \
CEQ_EXPECT_ALEMBIC_REVISION=20260514_outputs_job_storage_unique \
scripts/production-smoke.sh
```

### Tier D - Limited Commercial Pilot

**Status:** Planned.

Scope:

- Invite-only paying or design-partner cohort
- Dhanam-backed plan/credit source or manually approved billing bridge
- Server-side credit enforcement for all paid-gated actions
- Per-user queue/rate/spend limits
- Support channel and operator runbooks
- Daily smoke plus usage reconciliation

Exit evidence:

- 5-10 pilot accounts onboarded without engineer intervention
- All paid actions consume credits exactly once or fail closed
- No free user can invoke premium GPU/template paths through API bypass
- Operator can issue credit adjustment/refund through documented workflow
- Usage ledger reconciles with completed jobs and billing export

### Tier E - Commercial GA

**Status:** Planned.

Scope:

- Public pricing and self-serve checkout
- Production SLO/SLA posture approved by product/support
- Usage, invoice, and plan management available to customers
- Abuse controls and account suspension workflow
- Customer-facing docs, terms, privacy, acceptable-use, and support workflow
- GA launch checklist signed by product, engineering, platform, and support

Exit evidence:

- Launch checklist completed with owners/dates
- Paid signup, credit purchase, generation, output retrieval, and invoice receipt
  pass in production
- Alert drill and rollback drill completed
- First production incident runbook rehearsal completed
- Release notes and support macros published

---

## Commercial GA Execution Priority (ROI order)

Keep this priority sequence synchronized with the GA-Critical Execution Register above.

### What the first wave must unblock

These are not linear tickets; they are staged dependencies. The first two tracks
can and should run in parallel once the operator can create valid test identities
and a Janua admin session.

1. **Identity proof** (P0) and **runtime secrets** (P0) close together:
   - Browser login proof on `app.ceq.lol`
   - Admin `operations/status` proof
2. In parallel once 1 is complete, run production golden path proof:
   - Single authenticated image/thumbnail GPU completion proof
   - Output durability + gallery proof
3. In parallel with 2 (non-blocking for initial launch signal):
   - alert/rollback drill prep
   - credit plan/ledger policy decision
   - terms/privacy/AUP publish review

### 72-Hour ROI-first execution plan

Use this as the immediate remediation target after the Janua operator can supply
real credentials:

- **Lane A (P0 / highest ROI, ~0-2 days):** identity proof + callback secrets
  proof in one operator pass.
- **Lane B (P0 / highest ROI, ~1-3 days, parallel with Lane A):** seeded catalog
  evidence collection + authenticated GPU smoke once `operations/status` is green.
- **Lane C (P1, parallel with Lane B):** finalize billing policy decision,
  credit route expectations in production smoke, and alert/rollback drill prep.
- **Lane D (P2, post-lane A/B):** legal/commercial docs in customer-facing paths
  and a paid pilot rehearsal pack.

Dependency gates:

- Lane A must pass before any public commercial launch claim.
- Lane B cannot be green without Lane A.
- Lane D cannot be declared complete without Lane A/B and documented policy.

### Priority 1 — Identity and runtime proof

1. Real browser login on `app.ceq.lol`.
2. `GET /v1/operations/status` green for callback/webhook readiness.
3. Workflow-seed verification (`GET /v1/templates/` non-empty) or explicit seed-job evidence.
4. One authenticated GPU golden path proving queue → worker → callback → output.

### Progress snapshot for Priority 1 (2026-06-01)

- [x] Studio token route accepts Janua client secret (`invalid_grant` on bogus code)
- [x] Browser login + callback cookie state verified in production
- [ ] `GET /v1/operations/status` admin proof captured (currently `401 Invalid credentials. Signal corrupted.`)
- [ ] `/v1/templates/` seeded/catalog evidence captured (non-empty IDs)
- [ ] Authenticated job + gallery output proof captured
- [ ] `POST /v1/render/card` with Janua JWT confirms debit + cache semantics for paid path

### Priority 2 — Commercial control plane

4. Integrate plans with Dhanam or approved pilot bridge.
5. Replace role-only premium gates with Dhanam-backed entitlements.
6. Fund balances and enable render/GPU debits for a supported cohort.

### Progress snapshot for Priority 2 (2026-06-01)

- [x] Credit ledger schema and `/v1/credits/*` APIs exist in code
- [ ] `/v1/credits/balance` route is 401/403 for unauthenticated users and works with valid user token (currently `404` unauthenticated)
- [ ] Credit balance surfacing in Studio depends on production `credits` endpoint availability
- [x] Role-derived premium gating and per-user active-job caps landed
- [ ] No public plan/checkout flow in CEQ yet
- [ ] No Dhanam-backed entitlement source wired into API enforcement

#### Closure status for Priority 2

- [x] Credit model and API routes scaffolded in code
- [ ] Production-level credits endpoint proof (authn authz + balance payload contract)
- [ ] Dhanam checkout and funded entitlement source captured
- [ ] Plan-aware role and quota enforcement in live API paths

### Priority 3 — Reliability, support, and compliance

7. Replace role-derived caps with plan-aware quota/rate/spend controls.
8. Add/lock alert routing, runbooks, and rollback drill evidence.
9. Publish support macros and customer-facing terms/privacy/AUP/retention.

### Progress snapshot for Priority 3 (2026-06-01)

- [ ] Alert routing and drill evidence
- [ ] Support/incident runbooks linked to alert annotations
- [x] Support macros template started in `COMMERCIAL_LAUNCH_READINESS_PACK.md`
- [ ] Legal/commercial customer docs linked in customer-facing flows

### Priority 4 — Launch operations

10. Publish launch checklist, pricing/support limits, and legal links.
11. Execute a fresh-account paid-run rehearsal and attach evidence.

### Progress snapshot for Priority 4 (2026-06-01)

- [x] This roadmap now captures scope, gates, and dependencies
- [ ] No paid-run rehearsal with real credits/checkout completed

## Execution Sequence (ROI + parallelism)

| Sequence | Can run in parallel? | Owner(s) | Output |
|----------|----------------------|----------|--------|
| P0-1: Browser login proof + `operations/status` with admin JWT | No, sequential dependencies on operator credentials, but evidence capture can be parallelized across two operators | Studio/Janua/Platform | Identity readiness + runtime token readiness |
| P0-2: Authenticated GPU smoke (production) | Yes, once `P0-1` is green | API + Workers + Platform | End-to-end fulfillment evidence |
| P1-1: Dhanam plan contract + pilot bridge | Yes | Product + API | Billing source defined |
| P1-2: Entitlement hardening + quota policy | No (depends on plan contract source) | API | Revenue controls in API layer |
| P1-3: Alert + support + legal doc package | Yes | Platform + Support + Product | Operational launch posture |
| P2: Commercial pilot and launch rehearsal | No (requires P0-2 + P1-1/2 + P1-3) | All | Public launch readiness |

## GA Launch Evidence Log (to fill in on each production evidence run)

Each run should include one row in this section and a link to raw output.

- Date: 2026-06-01 — Public smoke evidence row completed (`CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh`)
- Date: 2026-06-01 — Public smoke command completed (`CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh`) with results in [`ops/evidence/2026-06-01-public-prod-smoke.md`](../ops/evidence/2026-06-01-public-prod-smoke.md)
- Date: 2026-06-01 — Endpoint matrix snapshot attempt in this session was inconsistent (DNS/connectivity); latest successful unauth matrix is `ops/evidence/2026-06-01b-prod-endpoints.csv`
- Date: 2026-06-01 — Added reproducible unauthenticated matrix capture path:
  `scripts/capture-public-endpoint-matrix.sh` (writes to `ops/evidence/<timestamp>-public-prod-endpoints.csv` when run in a healthy network)
- Date: 2026-06-01 — Session bootstrap evidence captured: `app.ceq.lol` login with `admin@madfam.io` returned `/api/auth/session` `user`, `roles`, `access_token`, and `ceq_access_token`/`ceq_refresh_token` `httpOnly` cookies.


## Implementation Tracks

### Track 0 - Program Control and Scope Freeze

Owner: Product + engineering lead

Tasks:

- Freeze commercial SKU set: Free, Pro Artist, Studio, internal/service-account
- Confirm whether pricing stays from Tulana/InterestGate or moves to Dhanam source
- Define supported templates for launch and mark unsupported PRD items as roadmap
- Define credit units for render, image GPU job, video GPU job, audio, and 3D
- Define success metrics: activation, first generation, paid conversion, support load

Acceptance:

- `docs/PRD.md` points to this plan for current commercial scope
- Launch template list and pricing assumptions have named owners
- No unpriced generation path is included in commercial GA scope

### Track 1 - Identity, Accounts, and Sessions

Owner: Studio + Janua operator

Tasks:

- Complete real browser login proof on `app.ceq.lol`
- Verify session refresh and logout end-to-end
- Decide customer account model: individual users, teams, or MADFAM org accounts
- Add account/tenant identifier to API authorization context if missing
- Record Janua logout P1 behavior and fix or document launch workaround

Acceptance:

- Browser login sets CEQ httpOnly cookies and Studio shell loads
- `GET /api/auth/session` returns user identity and usable access token
- API rejects cross-account access to jobs, outputs, templates, credits, and billing

### Track 2 - Runtime Fulfillment and GPU Reliability

Owner: API + workers + platform

Tasks:

- Verify `JOB_COMPLETION_CALLBACK_TOKEN` and `JOB_WEBHOOK_SECRET` in prod
- Run golden image GPU smoke and persist output to gallery
- Run cancel smoke and prove late worker success cannot overwrite cancellation
- Run multi-modal smoke for launch-supported template classes
- Establish worker capacity floor and cold-start/model-cache policy
- Define provider failover plan for Vast.ai/Furnace transition

Acceptance:

- `CEQ_STRICT_SMOKE=true scripts/production-smoke.sh` passes
- Completion dead-letter depth remains within threshold
- Capacity plan states max concurrent jobs, queue SLO, and spend cap

### Track 3 - Billing, Credits, and Entitlements

Owner: Product + Dhanam + API + Studio

Tasks:

- Integrate CEQ plans with Dhanam or document an approved pilot billing bridge
- Extend the initial credit ledger tables/API into Dhanam-backed plan funding
- Meter every billable generation and render action server-side; render cache-miss and GPU job debit/refund plumbing landed behind feature flags
- Make credit deduction idempotent against retries and callbacks
- Replace initial role-based premium template API enforcement with Dhanam-backed entitlements
- Replace role-derived plan caps with Dhanam-backed queue/rate/spend quotas
- Add usage summary and remaining credit views in Studio; account-menu balance landed 2026-06-01
- Add admin credit grant/adjustment workflow with audit trail

Acceptance:

- Free users cannot invoke premium templates by direct API call (initial role-based guard landed 2026-06-01)
- Paid users cannot exceed plan credits/queue limits without explicit overage policy (role-derived active-job caps landed 2026-06-01)
- Each completed paid job has exactly one ledger entry tied to job/output IDs
- Failed/cancelled jobs have clear refund/no-charge semantics

### Track 4 - Product UX and Commercial Onboarding

Owner: Studio + product

Tasks:

- Replace or supplement InterestGate with plan-aware upgrade/checkout states
- Add onboarding path: account created, plan selected, first template run
- Add empty, error, pending, exhausted-credit, and payment-failed states
- Add customer-visible job history, output download, and usage summary
- Lock launch template catalog and remove unsupported surfaces from primary UI
- Add customer docs links without exposing internal operator instructions

Acceptance:

- New user can reach first successful generation without operator help
- Exhausted credits and failed payments produce clear recovery paths
- Unsupported PRD surfaces do not appear as commercially available features

### Track 5 - Observability, Operations, and Support

Owner: Platform + CEQ on-call + support

Tasks:

- Confirm alert receivers for queue depth, stale jobs, dead letters, failures
- Link runbooks from alert annotations
- Add daily commercial smoke job with public, auth, operations, and billing checks
- Enable branch protection on `main`
- Define support severity matrix and escalation contacts
- Add support macros for login, failed job, missing credits, and billing issue
- Create incident comms template for customer-facing outages

Acceptance:

- Synthetic alert reaches on-call channel
- Support can answer top five expected tickets from docs/macros
- Release cannot merge or deploy without required CI gates

### Track 6 - Security, Abuse, and Compliance

Owner: Security + API + platform + legal/commercial

Tasks:

- Audit authz on jobs, outputs, templates, operations, credits, and billing routes
- Add audit logs for login, job submit, output access, credit changes, billing changes
- Add per-user/IP rate limits for login, render, job submit, and polling
- Define content policy and abuse escalation for generated assets
- Verify secrets are ExternalSecret/Vault-backed; no live secrets in repo
- Validate CORS allowlist and production docs exposure
- Publish customer-facing terms, privacy, acceptable-use, and data retention limits

Acceptance:

- API bypass tests fail closed for unpaid/premium and cross-account access
- Abuse controls are test-covered and enabled in prod
- Legal/commercial docs are linked from customer-facing flows

### Track 7 - Launch Cutover

Owner: Product + engineering + platform + support

Tasks:

- Run launch rehearsal with a fresh account and real payment path
- Run rollback drill for API, Studio, and worker digest regression
- Freeze release branch or tag GA digest commit
- Publish launch notes and known limits
- Monitor first 24 hours with named on-call owner

Acceptance:

- Commercial GA declaration is added to this document with evidence links
- Product, engineering, platform, and support sign off

---

## Immediate Implementation Tickets

1. [x] **DONE** Complete browser login proof on `app.ceq.lol` and capture authenticated session headers (`/api/auth/session` + httpOnly cookies).
2. [ ] **BLOCKED** Run `operations/status` with admin JWT and require callback/webhook readiness.
3. [ ] **BLOCKED** Seed/verify non-empty `/v1/templates/` catalog and capture a template UUID.
4. [ ] **BLOCKED** Run one authenticated GPU golden path (`job → complete → gallery`) with output URL evidence.
5. [ ] **IN PROGRESS** Add `/v1/credits/balance` and credit-route auth behavior into `CEQ_PUBLIC_ONLY=true` + authenticated smoke evidence.
6. [ ] **NOT STARTED** Enable credit plan source (Dhanam bridge or approved pilot billing bridge) and verify one paid action with debits.
7. [ ] **IN PROGRESS** Replace role-derived paid-template/API enforcement with entitlement-backed checks.
8. [ ] **IN PROGRESS** Finalize queue/rate/spend guardrails in API + worker path.
9. [ ] **NOT STARTED** Confirm alert routing + rollback drill evidence and link runbooks.
10. [ ] **NOT STARTED** Publish customer-facing legal/commercial docs (terms/privacy/AUP/retention/recovery) in Studio paths.
11. [ ] **NOT STARTED** Execute the paid pilot rehearsal (fresh account, login, generation, output, invoice/receipt path).

---

## Timeline

Assuming one focused engineering/platform lane and operator availability:

| Window | Target | Exit |
|--------|--------|------|
| Days 0-7 | Capped GA demo | Browser login + operations + one GPU golden path |
| Weeks 2-4 | Limited commercial pilot | Credits, API entitlement checks, quotas, support workflow |
| Weeks 4-6 | Pilot hardening | Billing reconciliation, alerts, support drills, abuse controls |
| Weeks 6-10 | Commercial GA | Self-serve launch pack, legal/commercial docs, release signoff |

Timeline risk is highest around GPU capacity, Dhanam integration scope, and
operator availability for production evidence.

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Treating capped demo as commercial GA | Premature sales/support load | Keep this doc as GA source of truth; require all gates |
| Billing integration scope expands | Launch delay | Start with minimum credit ledger + Dhanam checkout path |
| UI-only gating bypass | Revenue leakage and abuse | Enforce entitlements in API and test direct API calls |
| GPU capacity instability | Failed customer jobs | Capacity floor, queue limits, retry policy, provider fallback plan |
| Missing alert routing | Slow incident response | Synthetic alert drill before pilot |
| Manual operator steps remain | Non-repeatable launch | Convert to Enclii-first runbooks and record adapter gaps |
| Pricing confidence remains low | Wrong unit economics | Use pilot cohort caps and reconcile cost per completed output |

---

## Commercial GA Declaration Template

When all gates pass, add a dated section above the executive summary:

```markdown
## Commercial GA Declared - YYYY-MM-DD

- Identity: browser login/session/logout verified on app.ceq.lol
- Runtime: strict production smoke passed at <timestamp/log>
- Billing: paid signup/checkout/invoice verified through <provider>
- Credits: ledger reconciliation passed for <sample size>
- Entitlements: API bypass tests passed
- Quotas/abuse: enabled in production
- Observability: synthetic alert and rollback drill passed
- Support: macros/runbooks published at <paths>
- Legal/commercial: terms/privacy/AUP/pricing published at <paths>
- Signoff: product <name>, engineering <name>, platform <name>, support <name>
```

Do not add this declaration until evidence is attached.
