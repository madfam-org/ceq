# Janua Operator Guide — CEQ Studio

> **Purpose:** Unblock Phase 0 identity for CEQ full stability.  
> **Audience:** Janua operators, platform admins, CEQ on-call.  
> **Enclii-first:** Register clients and rotate secrets via Enclii/Janua adapters when available. Use Janua admin only as documented break-glass and record adapter gaps.

---

## Current blocker

CEQ Studio production login is **blocked** because Janua rejects the documented OAuth client:

| Symptom | Value |
|---------|-------|
| Error | `invalid_client: Unknown client_id` |
| Documented client ID | `jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk` |
| Production redirect URI | `https://app.ceq.lol/auth/callback` |
| Last verified | 2026-05-14 (still open as of 2026-05-22) |

Until this client is registered (or rotated), **no real user can complete browser login** on `app.ceq.lol`, and authenticated production smokes cannot run.

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

### 1. Register or rotate the client

- [ ] Client exists in Janua admin (`https://auth.madfam.io/admin`) or Enclii identity adapter
- [ ] Redirect URI `https://app.ceq.lol/auth/callback` is exact (no trailing slash mismatch)
- [ ] Grant types include `authorization_code` and `refresh_token`
- [ ] Client secret generated and stored in production secrets (not committed to git)

### 2. Verify Janua accepts the client (no browser required)

```bash
# Should NOT return invalid_client for authorize (expect 302/200, not OAuth error page)
curl -sS -o /dev/null -w "authorize: %{http_code}\n" \
  "https://auth.madfam.io/api/v1/oauth/authorize?client_id=jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk&redirect_uri=https%3A%2F%2Fapp.ceq.lol%2Fauth%2Fcallback&response_type=code&scope=openid+profile+email&state=%2F"
```

Token exchange requires a real authorization code — use browser acceptance for full proof.

### 3. Browser acceptance (production)

- [ ] Visit `https://app.ceq.lol/` (no cookies) → redirects to `/login?returnTo=%2F`
- [ ] Click through to Janua — **no** `invalid_client` error
- [ ] Complete credential login
- [ ] Land on `https://app.ceq.lol/auth/callback` then Studio shell
- [ ] `GET https://app.ceq.lol/api/auth/session` returns `access_token` + `user` (with session cookies)
- [ ] Studio loads workflows/queue via `/api/proxy` (requires live `api.ceq.lol` + Janua JWT)
- [ ] Sign out clears CEQ cookies and redirects through Janua logout

### 4. Post-login production smokes

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
