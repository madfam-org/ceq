# Platform Agent Handoffs — CEQ Studio Login Unblock

> **Last updated:** 2026-06-02
> **Goal:** Complete CEQ Tier B demo runtime gates: Vault-backed Janua ExternalSecret, repeatable authenticated smoke, operations status, and GPU proof.
> **CEQ repo state:** `main` branch state reflected in active commercial GA remediation notes (CI green; K8s wiring on main)
> **Janua P0:** ✅ OAuth client registered (`jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk`, authorize 302)  
> **CEQ engineering P0:** K8s manifests wired and fallback K8s Secret sync refreshed; current blocker is Vault-backed ExternalSecret health plus authenticated smoke.
> **Truth layer:** [`README.md`](./README.md), [`CEQ_CODEBASE_AUDIT_WRAPUP_2026-06-02.md`](./CEQ_CODEBASE_AUDIT_WRAPUP_2026-06-02.md), [`DOCS_EVIDENCE_AUDIT_2026-06-02.md`](./DOCS_EVIDENCE_AUDIT_2026-06-02.md)

> **2026-06-02 audit update:** Public smoke is green and `ceq-api`/`ceq-studio`
> are healthy, but ExternalSecret `ceq-janua-client-secret` is degraded because
> Vault `secret/ceq.JANUA_CLIENT_SECRET` is missing. The GitHub fallback sync
> refreshed the Kubernetes Secret but did not populate Vault. Authenticated
> smoke remains blocked on a real CEQ auth/admin token; GPU proof remains open.

---

## What is done (do not redo)

| Layer | Status | Evidence |
|-------|--------|----------|
| Janua OAuth client | ✅ | Authorize 302; token rejects bogus code with `invalid_grant` (not `invalid_client`) |
| GitHub repo secret | ✅ | `gh secret list --repo madfam-org/ceq` → `JANUA_CLIENT_SECRET` |
| Studio K8s mount | ✅ | `infrastructure/k8s/studio-deployment.yaml` — `JANUA_CLIENT_SECRET` secretKeyRef |
| ExternalSecret mapping | ✅ | `infrastructure/k8s/external-secret.yaml` — Vault `secret/ceq` property |
| CI / lint | ✅ | CEQ CI green on `aa4288b` |
| Public prod smoke | ✅ | `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh` |
| Playwright auth (mock Janua) | ✅ | 6/6 in CI |
| Operator script | ✅ | `scripts/sync-janua-client-secret-to-vault.sh` |

---

## Critical path (execute in order)

```text
[1] Enclii/Vault agent  →  secret/ceq.JANUA_CLIENT_SECRET in Vault
         ↓
[2] Platform/K8s agent  →  ExternalSecret sync + ceq-studio rollout
         ↓
[3] CEQ acceptance agent →  browser login + production-smoke with JWT
         ↓
[4] Janua agent (P1)      →  GET /logout 404 fix (parallel, non-blocking)
```

Agents **1** and **2** can be the same operator if they have Vault + cluster access.

---

## Coordinator prompt (paste to any orchestrator agent)

```markdown
Orchestrate CEQ Studio login unblock on production. Janua OAuth is registered;
CEQ repo has K8s wiring on main (aa4288b+). The only P0 blocker is syncing
JANUA_CLIENT_SECRET from GitHub Actions repo secret (madfam-org/ceq) into Vault
path secret/ceq so ExternalSecret → ceq-secrets → ceq-studio picks it up.

Read docs/PLATFORM_AGENT_HANDOFFS.md in madfam-org/ceq and dispatch:

1. Enclii/Vault agent — Vault patch (P0)
2. Platform/K8s agent — ExternalSecret + ArgoCD rollout verify (P0)
3. CEQ acceptance agent — browser + scripts/production-smoke.sh (P0 proof)
4. Janua agent — logout route 404 (P1, optional parallel)

Do not commit secrets. Report back with verification outputs (redacted).
Definition of done: real user login on https://app.ceq.lol + CEQ_AUTH_TOKEN smoke green.
```

---

## Agent 1 — Enclii / Vault (P0, blocking)

**Repo:** `madfam-org/enclii` (platform) + `madfam-org/ceq` (consumer manifests)  
**Docs:** `enclii/docs/infrastructure/SECRETS_MANAGEMENT.md`, `ceq/docs/JANUA_OPERATOR.md` §1

### Prompt

```markdown
You are the Enclii/Vault platform agent. Unblock CEQ Studio OAuth token exchange.

## Context
- CEQ ExternalSecret (`ceq/infrastructure/k8s/external-secret.yaml`) expects:
  - Vault path: `secret/ceq`
  - Property: `JANUA_CLIENT_SECRET`
- Source of truth for the value: GitHub Actions secret on `madfam-org/ceq`
  named `JANUA_CLIENT_SECRET` (already set 2026-05-23).
- Janua OAuth client ID (unchanged): `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk`

## Your tasks
1. Enclii-first: use Enclii secrets UI/CLI to write `JANUA_CLIENT_SECRET` to
   Vault `secret/ceq` if an adapter exists.
2. Break-glass: use Vault CLI/UI with operator credentials.
   - CEQ helper (operator runs locally with Vault auth):
     `scripts/sync-janua-client-secret-to-vault.sh`
   - Or: `vault kv patch secret/ceq JANUA_CLIENT_SECRET='…'`
3. NEVER commit the secret, log it, or paste it in PRs/issues.

## Verification (redacted output only)
- Confirm property exists without printing value:
  `vault kv get -format=json secret/ceq | jq 'has("data.data.JANUA_CLIENT_SECRET")'`
  → must return `true`
- Record timestamp and actor in Enclii audit log if available.

## Enclii adapter gap
If no Enclii path exists, record gap: "Enclii cannot sync GitHub repo secret
JANUA_CLIENT_SECRET → Vault secret/ceq for CEQ namespace."

## Hand off to Agent 2 when Vault patch succeeds.
```

---

## Agent 2 — Platform / K8s / ArgoCD (P0)

**Repo:** `madfam-org/ceq`  
**Cluster:** k3s Hetzner, namespace `ceq`, ArgoCD app `ceq-services`  
**Break-glass:** `ssh ssh.madfam.io` + `sudo k3s kubectl` (record gap if used)

### Prompt

```markdown
You are the CEQ platform/K8s agent. Ensure Studio pods receive JANUA_CLIENT_SECRET
after Vault sync (Agent 1 complete).

## Prerequisites
- Vault `secret/ceq.JANUA_CLIENT_SECRET` populated (Agent 1 ✅)

## Manifests (already on main — verify live cluster matches git)
- `infrastructure/k8s/external-secret.yaml` — JANUA_CLIENT_SECRET mapping
- `infrastructure/k8s/studio-deployment.yaml` — env secretKeyRef
- ArgoCD app tracks `infrastructure/k8s/`

## Your tasks
1. Confirm ExternalSecret reconciled:
   ```bash
   kubectl -n ceq get externalsecret ceq-secrets
   kubectl -n ceq describe externalsecret ceq-secrets | tail -20
   ```
2. Confirm K8s secret has key (byte length only — DO NOT decode in shared logs):
   ```bash
   kubectl -n ceq get secret ceq-janua-client-secret -o jsonpath='{.data.JANUA_CLIENT_SECRET}' | wc -c
   ```
   Expect non-zero (typically > 20 chars base64).
3. Sync / roll Studio:
   ```bash
   kubectl -n ceq rollout restart deployment/ceq-studio
   kubectl -n ceq rollout status deployment/ceq-studio --timeout=300s
   ```
   Or trigger ArgoCD sync on `ceq-services` if GitOps manages rollouts.
4. Verify pod env var **exists** (not value):
   ```bash
   POD=$(kubectl -n ceq get pod -l app=ceq-studio -o jsonpath='{.items[0].metadata.name}')
   kubectl -n ceq exec "$POD" -- sh -c 'test -n "$JANUA_CLIENT_SECRET" && echo ok'
   ```

## Failure modes
| Symptom | Fix |
|---------|-----|
| ExternalSecret SecretSyncedError | Vault path/property missing → Agent 1 |
| Pod CreateContainerConfigError | `ceq-secrets` missing key → ExternalSecret |
| Token exchange 401 invalid_client | Wrong secret vs Janua registration |
| Token exchange 500 / empty session | Secret empty in pod → rollout + Vault |

## Hand off to Agent 3 when Studio pods healthy with secret present.
```

---

## Agent 3 — CEQ acceptance / demo proof (P0)

**Repo:** `madfam-org/ceq`  
**Docs:** `docs/JANUA_OPERATOR.md` §4, `docs/GA_DEMO_DEFINITION.md` Tier B

### Prompt

```markdown
You are the CEQ acceptance agent. Prove end-to-end Studio login in production.

## Prerequisites
- Agent 1: Vault secret synced ✅
- Agent 2: ceq-studio pods running with JANUA_CLIENT_SECRET ✅

## Browser acceptance (docs/JANUA_OPERATOR.md §4)
1. Visit https://app.ceq.lol/ (no cookies) → `/login?returnTo=%2F`
2. Enter the Terminal → Janua login (must NOT show invalid_client)
3. Complete credential login → `/auth/callback` → Studio shell ("Signal acquired.")
4. DevTools → Application → Cookies on app.ceq.lol:
   - `ceq_access_token`, `ceq_refresh_token` present
5. `GET https://app.ceq.lol/api/auth/session` (with cookies) → 200 + user + access_token
6. Studio loads workflows/queue via `/api/proxy` (no 401 loop)

## Automated smokes
```bash
# Public (always)
CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh

# After login — extract JWT from session response or Janua token
export CEQ_AUTH_TOKEN='<janua-access-jwt>'
export CEQ_ADMIN_AUTH_TOKEN="${CEQ_AUTH_TOKEN}"

CEQ_RUN_OPERATIONS_STATUS=true \
CEQ_REQUIRE_OPERATIONS_STATUS=true \
scripts/production-smoke.sh
```

## Update docs when green (ceq repo PR)
- `docs/JANUA_OPERATOR.md` — mark CEQ-side blocker resolved
- `docs/GA_DEMO_DEFINITION.md` — Tier B identity checklist
- `docs/CEQ_STABILITY_ROADMAP.md` — Phase 0 complete

## Definition of done
- [ ] Browser login works for real user
- [ ] `/api/auth/token` returns 200 on OAuth callback
- [ ] `CEQ_AUTH_TOKEN` smoke passes operations status (if secrets provisioned)
- [ ] No secrets in commits
```

---

## Agent 4 — Janua logout route (P1, optional parallel)

**Repo:** Janua (`madfam-org/janua` or platform Janua deploy)  
**Symptom:** `GET https://auth.madfam.io/logout?client_id=…&post_logout_redirect_uri=…` → **404**

### Prompt

```markdown
You are the Janua platform agent (P1 — does NOT block login).

## Context
CEQ Studio logout calls:
GET {JANUA_URL}/logout?client_id=jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk&post_logout_redirect_uri=https://app.ceq.lol/

Live production returns HTTP 404. Login and token exchange work; only sign-out
redirect is broken.

## Your tasks
1. Expose GET /logout (or document correct OIDC end-session URL if different).
2. Accept post_logout_redirect_uri=https://app.ceq.lol/ and http://localhost:5801/
3. Verify:
   ```bash
   curl -sS -o /dev/null -w "%{http_code}\n" \
     "https://auth.madfam.io/logout?client_id=jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk&post_logout_redirect_uri=https%3A%2F%2Fapp.ceq.lol%2F"
   ```
   Expect 302/303 redirect, not 404.

## CEQ side (if Janua uses different endpoint)
Update `apps/studio/src/lib/auth.ts` `getLogoutUrl()` only if Janua documents
a different path — coordinate with CEQ agent after Janua fix lands.

## Not in scope
OAuth client registration (done). Token/authorize paths (working).
```

---

## Agent 5 — CEQ deploy / GitOps (monitoring)

**When:** After CI green; worker build ~20–30 min  
**Check:**

```bash
gh run list --repo madfam-org/ceq --workflow deploy.yaml --limit 1
```

Deploy workflow commits image digests to `infrastructure/k8s/kustomization.yaml`.
ArgoCD picks up within ~3 min. **Studio env mount does not require new image** —
it comes from manifest on `main` (`bcf0b6b+`), but new Studio digest from deploy
is still desirable.

### Prompt

```markdown
Monitor CEQ Deploy workflow on madfam-org/ceq main until success.
If failed: triage failed job (Build Studio / Worker / verify-ci / digest commit).
Do not force-push main. Fix forward with PR if needed.

Confirm ArgoCD ceq-services Healthy after digest commit lands.
```

---

## Quick verification matrix (any agent)

| Step | Command | Pass |
|------|---------|------|
| Janua authorize | `curl -sS -o /dev/null -w '%{http_code}' 'https://auth.madfam.io/api/v1/oauth/authorize?client_id=jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk&redirect_uri=https%3A%2F%2Fapp.ceq.lol%2Fauth%2Fcallback&response_type=code&scope=openid+profile+email&state=%2F'` | 302 |
| Public smoke | `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh` | exit 0 |
| Session (no cookie) | `curl -sS -w '\nHTTP:%{http_code}\n' https://app.ceq.lol/api/auth/session` | 401 |
| Vault key exists | `vault kv get -format=json secret/ceq \| jq 'has("data.data.JANUA_CLIENT_SECRET")'` | true |
| K8s secret key | `kubectl -n ceq get secret ceq-janua-client-secret -o jsonpath='{.data.JANUA_CLIENT_SECRET}' \| wc -c` | >0 |
| Pod has env | `kubectl -n ceq exec deploy/ceq-studio -- sh -c 'test -n "$JANUA_CLIENT_SECRET" && echo ok'` | ok |

---

## Related CEQ docs

| Doc | Purpose |
|-----|---------|
| [`JANUA_AGENT_HANDOFF.md`](./JANUA_AGENT_HANDOFF.md) | Janua OAuth contract (P0 done) |
| [`JANUA_OPERATOR.md`](./JANUA_OPERATOR.md) | CEQ operator checklist |
| [`GA_DEMO_DEFINITION.md`](./GA_DEMO_DEFINITION.md) | Tier B demo acceptance |
| [`CEQ_STABILITY_ROADMAP.md`](./CEQ_STABILITY_ROADMAP.md) | Full stability program |
| [`CEQ_IDENTITY_AND_DEMO_WRAPUP.md`](./CEQ_IDENTITY_AND_DEMO_WRAPUP.md) | Session wrap-up and doc index |
| [`PRODUCTION_DEPLOYMENT.md`](./PRODUCTION_DEPLOYMENT.md) | Deploy + secrets |
| [`COMMERCIAL_LAUNCH_READINESS_PACK.md`](./COMMERCIAL_LAUNCH_READINESS_PACK.md) | Commercial launch evidence and support macros |

---

## Coordinator session outcomes (2026-05-23)

Agents 1→2→3 dispatched per this doc. Agent 4 (Janua logout) run in parallel.

| Agent | Result | Evidence (redacted) |
|-------|--------|---------------------|
| **1 Vault** | Historical 2026-05-23 result: ❌ **Blocked** — automation could not read GitHub secret value | `ceq-secrets` had **no** `JANUA_CLIENT_SECRET` key; 10 other keys present. 2026-06-01 token-route proof indicates deployed Studio now has an accepted secret. |
| **2 K8s** | Historical 2026-05-23 result: ⏸ Waiting on Agent 1 | 2026-06-01 token-route proof indicates the deployed Studio now has an effective secret; verify cluster directly before secret rotation. |
| **3 Acceptance** | ⏳ Partial | `CEQ_PUBLIC_ONLY=true scripts/production-smoke.sh` **PASS**; session without cookies **401** as expected; browser login captured; operations/runtime smoke still pending. |
| **4 Janua logout** | 🔧 Fix in `janua` repo | `GET /logout` + OIDC `end_session_endpoint`; **prod still 404** until Janua deploy |

**Historical operator unblock (Agent 1):** run `scripts/sync-janua-client-secret-to-vault.sh` with Vault auth
(paste secret from GitHub Actions settings — never commit). Current fastest proof is browser acceptance with real credentials, then authenticated `scripts/production-smoke.sh`.

**Automation limits:** `gh` cannot read secret values; local `vault` CLI absent; `ssh.madfam.io`
timed out; Enclii `ops secrets vault` is inspect-only. CEQ deploy workflow intentionally has
no kube-apiserver access from ARC runners (NetworkPolicy).

Consolidated wrap-up: [`CEQ_IDENTITY_AND_DEMO_WRAPUP.md`](./CEQ_IDENTITY_AND_DEMO_WRAPUP.md).

---

## Enclii adapter gaps to record

| Gap | Break-glass used | Follow-up |
|-----|------------------|-----------|
| GitHub → Vault sync for CEQ Janua secret | Vault CLI / `sync-janua-client-secret-to-vault.sh` | Enclii secret sync adapter |
| ArgoCD / rollout verification | kubectl (in-cluster) | Enclii deploy status API |
| Janua logout route missing | Janua PR + deploy (`GET /logout` implemented locally) | OIDC end-session on `auth.madfam.io` |
