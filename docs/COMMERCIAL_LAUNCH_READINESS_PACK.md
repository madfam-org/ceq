# CEQ Commercial Launch Readiness Pack

> **Purpose:** Keep commercial launch readiness and support work in one place. This
> document tracks evidence, support responses, alert routing, and legal/commercial
> assets required for paid GA.
> 
> **Related:** [`COMMERCIAL_GA_REMEDIATION_PLAN.md`](./COMMERCIAL_GA_REMEDIATION_PLAN.md), [`GA_DEMO_DEFINITION.md`](./GA_DEMO_DEFINITION.md), [`CEQ_STABILITY_ROADMAP.md`](./CEQ_STABILITY_ROADMAP.md), [`PRODUCTION_DEPLOYMENT.md`](./PRODUCTION_DEPLOYMENT.md)

---

## Owners

- Product: scope and acceptance criteria owner.
- Engineering: API and Studio readiness owner.
- Platform: deployment, secrets, alerting, and runbook owner.
- Support: customer response playbook owner.

## Operational evidence pack

### Evidence repository

- 2026-06-01 public smoke evidence: [`ops/evidence/2026-06-01-public-prod-smoke.md`](../ops/evidence/2026-06-01-public-prod-smoke.md)
  - `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh` is green (limited scope).
  - Fresh public endpoint matrix runs use:

```bash
scripts/capture-public-endpoint-matrix.sh
```

- Latest successful snapshot on record: `ops/evidence/2026-06-01T221752Z-public-prod-endpoints.csv`
- Earlier successful snapshots: `ops/evidence/2026-06-01T2200-public-prod-endpoints.csv`,
  `ops/evidence/2026-06-01T212236Z-public-prod-endpoints.csv`

### Required evidence for paid launch

Before commercial GA, collect and archive the following:

- `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh` green.
- Real browser login proof on `app.ceq.lol` with Janua credentials.
- `GET /api/auth/session` returns `user` + token when session cookies exist.
- `GET /v1/operations/status` returns callback/webhook readiness and alembic revision.
- At least one authenticated GPU template submission completes end-to-end.
- `POST /v1/render/*` cache-miss billing semantics are coherent for the paid flow.
- `/v1/credits/*` endpoints are available in production and produce expected auth-aware responses when used in the paid flow.
- Cancel smoke passes in production and no stale failed completion replay without explicit action.
- `/billing` checkout buttons are enabled only after Dhanam catalog, entitlement, and paid-run evidence is captured.

Use one date-stamped checklist row for each production run:

- Environment: prod
- Operator: 
- Template UUIDs used: 
- CEQ_AUTH_TOKEN source: 
- Operations status: 
- Dead letters: 
- Gallery proof: 

### Evidence artifact schema

Store each run as:

- Date: `YYYY-MM-DD`
- Log path: `ops/evidence/$(date)` (or equivalent)
- `prod-smoke.log` (from `scripts/production-smoke.sh`)
- `ops-status.json` (captured `GET /v1/operations/status` response)
- `golden-job.md` with template UUID, job ID, output URL, and callback path

Minimum evidence gates for GA-adjacent launch:

- `GET /v1/templates/` returns `total > 0` (or seeded UUID evidence is recorded)
- `GET /v1/credits/balance` returns `401/403` unauthenticated and success with `200` for authenticated user
- Browser login on `app.ceq.lol` persists session cookies and loads Studio shell
- `operations/status` shows callback token configured and alembic revision
- One authenticated GPU golden path with queue completion + output in gallery
- Dhanam checkout uses product `ceq` with tiers `pro_artist` and `studio`; `NEXT_PUBLIC_CEQ_CHECKOUT_ENABLED=true` is allowed only after entitlement source proof.

### Documents and contracts

- `docs/COMMERCIAL_GA_REMEDIATION_PLAN.md`
- `docs/GA_DEMO_DEFINITION.md`
- `docs/CEQ_STABILITY_ROADMAP.md`
- `docs/JANUA_OPERATOR.md`
- `docs/PLATFORM_AGENT_HANDOFFS.md`
- `docs/PRD.md`

## Support macros

### 1) Login fails with Janua errors

Symptoms: redirect loop, invalid_client, 401 in `/api/auth/session`.

Operator flow:

- Ask for the auth callback URL and screen capture.
- Confirm Studio environment has `JANUA_CLIENT_SECRET` present in `ceq-janua-client-secret`.
- Re-run the login check in `docs/JANUA_OPERATOR.md`.
- Confirm `POST /api/auth/token` responds `200` on valid Janua code.
- Escalate to Janua team if callback is failing and Secret is present.

### 2) Job stays queued or never completes

Symptoms: long-running jobs with no status updates.

Operator flow:

- Check `/v1/jobs/{id}` status and Redis queue depth.
- Confirm worker deployment is Running and `JOB_COMPLETION_CALLBACK_TOKEN` is set.
- If callback is redacted in logs, confirm operations endpoint shows `callback_token_configured`.
- Use `/v1/operations/completion-dead-letters` and replay only after upstream fix confirmation.

### 3) Credits deducted but output not visible

Symptoms: debit entries exist, no gallery output.

Operator flow:

- Check job outputs endpoint: `/v1/jobs/{id}/outputs` and gallery endpoint.
- Check credit ledger entries for the job id.
- Validate output storage URI points to `ceq-assets` bucket and is signed/published.
- If mismatch persists, use dead-letter queue and callback replay after idempotent checks.

### 4) Cancel works slowly or fails

Symptoms: cancel request returns 204 but job completes.

Operator flow:

- Verify `DELETE /v1/jobs/{id}` returns 200/204.
- Poll job for `cancel_requested_from_status` and `cancelled` terminal state.
- If late worker completion races with cancel, confirm worker contract does not overwrite `cancelled`.

### 5) Support requests about missing invoice or plan

Symptoms: user reports account entitlement mismatch.

Operator flow:

- Ask for the request timestamp and user id.
- Validate credits via `/v1/credits/balance`.
- Check credit ledger for grant/consume entries around issue window.
- If no paid bridge exists, provide trial/upgrade path as approved by Product.

## Alert and incident readiness

### Required alert links

- Queue depth over threshold.
- API 5xx rate increases.
- Completion dead letters over threshold.
- Redis heartbeat not available from `operations/status`.

Each alert must route to:

- on-call channel
- incident bridge channel
- support bridge channel

Each alert should include:

- runbook link
- run command for remediation
- severity owner

### Runbook checklist

- Escalate to on-call after 5xx or dead-letter threshold breach.
- Capture job id, API request id, and last callback status.
- Run `CEQ_RUN_OPERATIONS_STATUS=true` smoke with admin token.
- Confirm callback/webhook secrets and restart worker only after state review.

## Legal and customer docs

Add or confirm links in customer-facing flows for:

- Terms of Service
- Privacy policy
- Acceptable use policy
- Retention policy for generated media
- Refund and support terms

Current Studio routes:

- `/legal/terms`
- `/legal/privacy`
- `/legal/acceptable-use`
- `/legal/retention`
- `/legal/refunds`

No customer-facing launch should proceed without these links in Studio shell or
support paths.

## Launch completion criteria

- All evidence rows in this pack are complete and reviewed by product.
- Support macros are published and tested monthly.
- Alert channels and on-call runbook are connected end-to-end.
- Legal/commercial links are present in customer-facing paths.

This is not a substitute for external legal counsel or billing onboarding; it is
the launch control artifact for CEQ operators and the support desk.
