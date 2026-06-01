# CEQ Browser Login Proof (2026-06-01)

## Scope
- Real browser OAuth flow via Janua production UI
- Environment: `https://app.ceq.lol`
- User: `admin@madfam.io`
- Outcome: authenticated Studio shell loaded, session endpoint returned user and access token

## Procedure
1. Opened `https://app.ceq.lol` and reached Janua authorize redirect.
2. Performed Janua form login with production credentials.
3. Landed on `https://app.ceq.lol/auth/callback` and observed Studio shell render.
4. Confirmed `/api/auth/session` returns valid session payload:
   - `status: 200`
   - includes `access_token`, `user.email = admin@madfam.io`, `user.id`
   - includes `roles: ["admin"]`
5. Confirmed app shell rendered with `/v1/workflows` navigation and authenticated context.

## Follow-on
- Using this session token for authenticated API smoke, public/auth gates pass.
- `GET /v1/operations/status` still returns `401` with `Invalid credentials. Signal corrupted.`
