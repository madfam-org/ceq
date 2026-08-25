# Service Credentials — CEQ machine-to-machine auth

> **Purpose:** Let batch/machine callers use `/v1/render/*` and `/v1/jobs/*`
> without a browser session.
> **Audience:** Janua operators, CEQ on-call, batch-driver authors.
> **Pattern:** ADR-006 Janua `client_credentials` — the proven ecosystem edge
> (fashion-cabinet → yantra4d, live since 2026-08-22; zavlo → karafiel;
> routecraft → dhanam).
> **Enclii-first:** register clients and store secrets via Enclii/Janua
> adapters where available; treat Janua admin/DB access as documented
> break-glass and record any adapter gap.

---

## What changed in CEQ

Before: every CEQ endpoint required a Janua **user** JWT via
`Depends(get_current_user)`, including `GET /v1/render/templates`. A batch
driver had no way in.

Now, additively:

- `get_current_user` stays the **human** dependency. A machine token there is a
  **403** — nothing about human behavior changed anywhere.
- `get_service_or_user` accepts a human **or** a service principal, and backs
  the machine-reachable surface only.

### Endpoints reachable with a service token

| Endpoint | Method |
|---|---|
| `/v1/render/card` | POST |
| `/v1/render/thumbnail` | POST |
| `/v1/render/audio` | POST |
| `/v1/render/3d` | POST |
| `/v1/render/templates` | GET |
| `/v1/jobs/` | GET |
| `/v1/jobs/{job_id}` | GET |
| `/v1/jobs/{job_id}/status` | GET |
| `/v1/jobs/{job_id}` | DELETE |
| `/v1/jobs/{job_id}/outputs` | GET |
| `/v1/jobs/{job_id}/ws` | WebSocket (same scope gate) |

### Deliberately NOT reachable with a service token

`/v1/workflows/*`, `/v1/assets/*`, `/v1/credits/*`, `/v1/outputs/*`,
`/v1/operations/*`, and `POST /v1/templates/{id}/fork` + `.../run`.

`fork` writes a persistent user-owned grimoire row and `run` submits GPU work
with credit implications — both are user-specific surfaces. `GET /v1/templates`
reads were already unauthenticated and are unaffected. If a batch driver later
needs `run`, widen it deliberately in its own PR with its own scope.

---

## Accepted claim shape

Emitted by Janua's `_get_client_credentials_claims` +
`_handle_client_credentials_grant`:

```json
{
  "sub":        "service-account:<client_id>",
  "email":      "<slug>@service.auth.madfam.io",
  "client_id":  "<client_id>",
  "token_use":  "client_credentials",
  "actor_type": "service_account",
  "scope":      "ceq:render",
  "aud":        "ceq-api",
  "roles":      ["service_account"],
  "ceq_tier":   "madfam",
  "tier":       "community",
  "exp":        "<~1h>"
}
```

Two things gate acceptance:

1. **Audience** — verified in the JWKS decode against `JANUA_AUDIENCE`. A token
   minted for `yantra4d-api` never authenticates against CEQ.
2. **Scope** — must contain `SERVICE_PRINCIPAL_SCOPE` (default `ceq:render`).
   Missing it is a **403**, not a 401.

`sub` is deliberately not a UUID; CEQ derives a stable UUIDv5 principal id from
`client_id` instead (see the API README's Authentication section).

---

## Operator runbook

### 1. Check whether a client already exists — BEFORE registering

> [!WARNING]
> Janua's register endpoint UPSERTS BY AUDIENCE — one machine client per
> audience; registering a same-audience client silently hijacks the existing row
> and upserts never return a secret; GET /internal/by-name/ or DB-inspect BEFORE
> register.

Concretely: if any client already holds audience `ceq-api`, a fresh
`POST /api/v1/oauth/clients/register` for that audience will **overwrite that
client in place** and hand you back no `jns_` secret — leaving you with a
hijacked row and no usable credential, and breaking whatever was using the
previous client. Inspect first, every time:

```bash
# Preferred: name lookup
curl -sS -H "X-Internal-API-Key: $JANUA_INTERNAL_API_KEY" \
  "https://auth.madfam.io/api/v1/oauth/clients/internal/by-name/ceq-batch-driver"

# Or DB-inspect the audience directly (break-glass)
#   select client_id, name, audience, is_confidential, is_active
#     from oauth_clients where audience = 'ceq-api';
```

If a client with audience `ceq-api` already exists, **do not register** — reuse
it (and rotate its secret if you need a fresh one) or pick a distinct audience.

### 2. Register (only if step 1 found nothing)

Register a **confidential** client with:

- `audience`: `ceq-api` (must match CEQ's `JANUA_AUDIENCE`)
- `allowed_scopes` including `ceq:render`
- `grant_types` including `client_credentials`

The `ceq:` namespace is what makes Janua emit `ceq_tier: "madfam"`.

### 3. Store the secret

> [!IMPORTANT]
> Put the `jns_` secret in Vault. **Never** paste it into a transcript, a PR
> body, an issue, a chat message, or a log line. If one is ever exposed, treat
> it as compromised and rotate immediately.

Vault path follows the existing CEQ convention (`secret/ceq`, alongside
`JANUA_CLIENT_SECRET`); sync to Kubernetes with an ExternalSecret and mount it
into the consumer, not into CEQ. **CEQ never sees the secret** — it only
verifies the resulting RS256 token via JWKS.

### 4. Configure CEQ

```
JANUA_AUDIENCE=ceq-api
JANUA_JWKS_URL=https://auth.madfam.io/.well-known/jwks.json
JANUA_ISSUER=https://auth.madfam.io
SERVICE_PRINCIPALS_ENABLED=true        # default
SERVICE_PRINCIPAL_SCOPE=ceq:render     # default
RATE_LIMIT_SERVICE_PRINCIPAL=100/minute # default
```

`JANUA_AUDIENCE` is what binds machine tokens to CEQ. If it is left empty,
audience verification is skipped for **all** tokens (pre-existing behavior) —
set it before enabling machine access in production.

---

## Consumer side (the batch driver)

Mint on demand, cache in memory, re-mint ~60s before `exp` — never bake a static
token into the environment. `POST /api/v1/oauth/token` with
`grant_type=client_credentials`, HTTP Basic `client_id:client_secret`, and
`scope=ceq:render`. The reference implementation is
`fashion-cabinet/apps/api/body_render.py` (`_janua_service_token`).

Send an honest `User-Agent`: urllib's default is on Cloudflare's
banned-signature list (Error 1010 at the auth edge).

---

## Rate limiting

Machine callers land in a **separate limiter bucket** keyed
`service:<client_id>`; humans stay on `user:<uuid>`. The buckets are disjoint by
construction, so a backfill cannot evict human callers.

At the 100/minute default a 720-object backfill takes roughly 8 minutes. Retune
with `RATE_LIMIT_SERVICE_PRINCIPAL` rather than a code change. Note the limiter
is only `enabled` in production (`settings.is_production`), unchanged.

---

## Kill switch

Set `SERVICE_PRINCIPALS_ENABLED=false` and restart. Machine tokens then fail
closed with a 401 and a `service principals disabled` warning in the logs;
human authentication is completely unaffected. The rejection is terminal — CEQ
does not spend an introspection round-trip asking Janua's *userinfo* endpoint
about a token that has no user behind it.
