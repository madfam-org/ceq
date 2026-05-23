# Janua Operator Guide — CEQ Studio

> **Purpose:** Unblock Phase 0 identity for CEQ full stability.  
> **Audience:** Janua operators, platform admins, CEQ on-call.  
> **Janua-side agent:** See [`JANUA_AGENT_HANDOFF.md`](./JANUA_AGENT_HANDOFF.md) for the complete cross-repo handoff.  
> **Demo context:** [`GA_DEMO_DEFINITION.md`](./GA_DEMO_DEFINITION.md)  
> **Enclii-first:** Register clients and rotate secrets via Enclii/Janua adapters when available. Use Janua admin only as documented break-glass and record adapter gaps.

---

## Current blocker

### Janua-side (resolved 2026-05-23)

OAuth client **`jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk`** is registered in production
Janua. Authorize returns **302** to login (not `invalid_client`).

| Check | Status |
|-------|--------|
| §9.1 authorize | ✅ 302 |
| §9.2 token (bogus code) | ✅ `invalid_grant` (client accepted) |
| §9.4 JWKS / issuer | ✅ `https://auth.madfam.io` |
| §9.5 GET `/logout` | ⚠️ 404 — non-blocking for login; see [Logout follow-up](#logout-follow-up) |

### CEQ-side (operator action required)

Studio token exchange requires **`JANUA_CLIENT_SECRET` at runtime**. As of
2026-05-23:

- GitHub Actions repo secret `JANUA_CLIENT_SECRET` is set (`madfam-org/ceq`)
- **Vault** path `secret/ceq` must include property `JANUA_CLIENT_SECRET`
  (ExternalSecret syncs to `ceq-secrets`)
- **`studio-deployment.yaml`** mounts the secret (landed in repo; ArgoCD must roll pods)

Until Vault sync + ArgoCD rollout complete, browser login may fail at token
exchange even though Janua authorize succeeds.

**Previous symptom (resolved on authorize path):**

| Symptom | Value |
|---------|-------|
| Error | ~~`invalid_client: Unknown client_id`~~ |
| Documented client ID | `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk` |
| Production redirect URI | `https://app.ceq.lol/auth/callback` |

Local/CI auth behavior is covered by **mocked Janua** Playwright tests (`apps/studio/e2e/auth.spec.ts`). Those tests do **not** replace live Janua registration.

---

## What CEQ needs from Janua

### OAuth client registration

Register (or re-register) an OIDC client with these fields:

| Field | Required value |
|-------|----------------|
| **Client name** | `CEQ Studio` |
| **Client ID** | `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk` *(preferred — matches repo/env)* **or** a new ID if rotating |
| **Grant types** | `authorization_code`, `refresh_token` |
| **Scopes** | `openid`, `profile`, `email` |
| **Production redirect URI** | `https://app.ceq.lol/auth/callback` |
| **Development redirect URI** | `http://localhost:5801/auth/callback` |
| **Post-logout redirect** | `https://app.ceq.lol/` (and `http://localhost:5801/` for dev) |

### Janua OIDC endpoints (production)

| Step | URL |
|------|-----|
| Authorization | `https://auth.madfam.io/api/v1/oauth/authorize` |
| Token | `https://auth.madfam.io/api/v1/oauth/token` |
| UserInfo | `https://auth.madfam.io/api/v1/oauth/userinfo` |
| JWKS | `https://auth.madfam.io/.well-known/jwks.json` |

Studio uses these for browser login, token exchange (`/api/auth/token`), refresh (`/api/auth/refresh`), and session bootstrap (`/api/auth/session`).

### Secrets to provision after registration

| Secret | Where | Notes |
|--------|-------|-------|
| `JANUA_CLIENT_SECRET` | K8s `ceq-secrets` / ExternalSecret | Server-side token exchange + refresh only |
| `NEXT_PUBLIC_JANUA_CLIENT_ID` | Studio build arg / GitHub var `CEQ_PUBLIC_JANUA_CLIENT_ID` | Public; rebuild Studio if it changes |
| `NEXT_PUBLIC_JANUA_URL` | Studio build arg | Default `https://auth.madfam.io` |

**If the client ID rotates:**

1. Update Janua client registration.
2. Update `NEXT_PUBLIC_JANUA_CLIENT_ID` in Studio deploy vars.
3. Update `JANUA_CLIENT_SECRET` in `ceq-secrets`.
4. Redeploy Studio via GitOps (ArgoCD reconciles new digest).
5. Re-run acceptance checks below.

---

## Operator checklist

### 1. Sync `JANUA_CLIENT_SECRET` to Vault (Enclii-first)

The client secret lives in GitHub Actions (`gh secret list --repo madfam-org/ceq`).
**Do not commit it.** Copy into Vault at `secret/ceq` property `JANUA_CLIENT_SECRET`
so ExternalSecret can sync to K8s `ceq-secrets`.

```bash
# Verify GitHub secret exists (name only — never print the value)
gh secret list --repo madfam-org/ceq | rg JANUA_CLIENT_SECRET

# Enclii-first: use Enclii secrets UI/CLI when adapter supports Vault sync.
# Break-glass: write to Vault path secret/ceq → property JANUA_CLIENT_SECRET
# Then confirm ExternalSecret reconciled:
# kubectl -n ceq get externalsecret ceq-secrets
# kubectl -n ceq get secret ceq-secrets -o jsonpath='{.data.JANUA_CLIENT_SECRET}' | wc -c
# (expect non-zero byte length; do not decode in shared logs)
```

Record Enclii adapter gap if Vault write required raw operator access.

Janua client registration (complete 2026-05-23):

- [x] Client `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk` registered (`ceq-studio`)
- [x] Redirect URIs and grant types configured
- [ ] Vault `JANUA_CLIENT_SECRET` synced → `ceq-secrets` → Studio pods rolled

### 2. Confirm Studio runtime secret mount (in-repo; verify in cluster)

`infrastructure/k8s/studio-deployment.yaml` mounts `JANUA_CLIENT_SECRET` from
`ceq-secrets`. After Vault sync + ArgoCD reconcile:

- [ ] `kubectl -n ceq get pods -l app=ceq-studio` — all Running
- [ ] Studio pod has env `JANUA_CLIENT_SECRET` (verify presence only — do not log value)
- [ ] `POST /api/auth/token` succeeds after browser OAuth callback

### 3. Verify Janua accepts the client (no browser required)

```bash
# Should NOT return invalid_client for authorize (expect 302/200, not OAuth error page)
curl -sS -o /dev/null -w "authorize: %{http_code}\n" \
  "https://auth.madfam.io/api/v1/oauth/authorize?client_id=jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk&redirect_uri=https%3A%2F%2Fapp.ceq.lol%2Fauth%2Fcallback&response_type=code&scope=openid+profile+email&state=%2F"
```

Token exchange requires a real authorization code — use browser acceptance for full proof.

### 4. Browser acceptance (production)

- [ ] Visit `https://app.ceq.lol/` (no cookies) → redirects to `/login?returnTo=%2F`
- [ ] Click through to Janua — **no** `invalid_client` error
- [ ] Complete credential login
- [ ] Land on `https://app.ceq.lol/auth/callback` then Studio shell
- [ ] `GET https://app.ceq.lol/api/auth/session` returns `access_token` + `user` (with session cookies)
- [ ] Studio loads workflows/queue via `/api/proxy` (requires live `api.ceq.lol` + Janua JWT)
- [ ] Sign out clears CEQ cookies and redirects through Janua logout

### 5. Post-login production smokes

After Janua **and** runtime callback secrets are provisioned (see `docs/PRODUCTION_DEPLOYMENT.md`):

```bash
CEQ_AUTH_TOKEN=<janua-jwt-from-login> \
CEQ_ADMIN_AUTH_TOKEN=<admin-jwt-if-different> \
CEQ_TEMPLATE_ID=<seeded-template-uuid> \
CEQ_RUN_OPERATIONS_STATUS=true \
scripts/production-smoke.sh
```

Full stability gate:

```bash
CEQ_STRICT_SMOKE=true \
CEQ_AUTH_TOKEN=<jwt> \
CEQ_ADMIN_AUTH_TOKEN=<admin-jwt> \
CEQ_TEMPLATE_ID=<uuid> \
CEQ_CANCEL_TEMPLATE_ID=<long-running-uuid> \
scripts/production-smoke.sh
```

---

## Host routing reference

| Host | Purpose |
|------|---------|
| `ceq.lol` | Public marketing/landing only |
| `app.ceq.lol` | Authenticated Studio (session cookie gate) |
| `api.ceq.lol` | FastAPI (Janua JWT on protected routes) |
| `ws.ceq.lol` | Job WebSocket streams (token query param today) |

OAuth callback **must** use `app.ceq.lol`, not `ceq.lol`.

---

## Logout follow-up

Janua returns **404** for `GET https://auth.madfam.io/logout?client_id=…&post_logout_redirect_uri=…`.
Login and token exchange are unblocked; sign-out may fail to redirect cleanly until
Janua exposes the logout route or CEQ switches to the documented OIDC end-session
endpoint. Track as P1 — not a blocker for capped GA demo login.

---

## Troubleshooting

| Issue | Likely cause | Fix |
|-------|--------------|-----|
| `invalid_client` on login | Client not registered or wrong ID | Re-register client; align `NEXT_PUBLIC_JANUA_CLIENT_ID` |
| `redirect_uri_mismatch` | Janua redirect list doesn't match | Add exact `https://app.ceq.lol/auth/callback` |
| Callback succeeds but Studio empty | Session cookies not set | Check `JANUA_CLIENT_SECRET`; inspect `/api/auth/token` response |
| `/api/proxy` 401 | API rejects Janua JWT | Verify API `JANUA_URL`/JWKS config matches `auth.madfam.io` |
| Login works locally, not prod | Stale Studio image or wrong build args | Confirm ArgoCD rolled Studio digest; check deploy workflow vars |

---

## Related docs

- [`GA_DEMO_DEFINITION.md`](./GA_DEMO_DEFINITION.md) — capped GA demo scope, Tier B checklist, timeline
- [`JANUA_AGENT_HANDOFF.md`](./JANUA_AGENT_HANDOFF.md) — complete handoff for Janua-side agents
- `docs/CEQ_STABILITY_ROADMAP.md` — Phase 0 acceptance + full stability gates
- `docs/PRODUCTION_DEPLOYMENT.md` — secrets, deploy checklist, smoke runner
- `apps/studio/e2e/auth.spec.ts` — CI auth regression (mocked Janua)
- `scripts/production-smoke.sh` — production acceptance automation

---

## Enclii adapter gap (record if applicable)

If Janua client registration still requires raw Janua admin access, record:

- **Gap:** Enclii identity adapter does not yet provision Janua OAuth clients for CEQ Studio
- **Break-glass used:** Janua admin UI at `https://auth.madfam.io/admin`
- **Follow-up:** Open Enclii adapter issue; remove raw-admin from routine runbooks once adapter ships
