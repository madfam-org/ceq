# Client Brand-Asset DAM (`/v1/brand-kits`)

ceq is the ecosystem's designated **client-brand DAM** — the system-of-record
for a client's *source* brand book (palette, typography, logos, usage rules) and
the binary brand assets behind it. This is the storage / source-of-truth half;
ceq's existing `/v1/render` is the generation half that consumes these kits.

> This is the curated, multi-tenant layer. It is deliberately separate from the
> per-principal scratch `Asset` model (`/v1/assets`), which stores a user's own
> ML checkpoints/LoRAs keyed by `user_id`. Brand data is tenant-scoped, durable,
> and versioned — not user scratch.
>
> Ecosystem record: this designation is captured in solarpunk-foundry §IV.7
> (companion PR).

## Entities

| Table | Role |
|---|---|
| `brand_clients` (`Client`) | Tenant root. One row per Janua org, bound by `janua_org_id`. |
| `brand_kits` (`BrandKit`) | A client's brand book as **structured** source-of-truth (palette / typography / logos / guidelines) + a monotonic `version`. |
| `brand_assets` (`BrandAsset`) | A single **binary** file (logo, font, guideline PDF, photo) stored in R2, mirroring the `Asset` storage shape. |

`Client 1—* BrandKit 1—* BrandAsset`. A `BrandAsset` also denormalizes
`client_id` so the tenant fence never needs a join.

## Tenancy rule (security-critical — mirrors acervo)

**The tenant comes from the Janua token, never the URL.**

- Every tenant-scoped route resolves the caller's `Client` from the verified
  `JanuaUser.org_id` claim (`resolve_tenant`). No route names a tenant/client/org
  in its path, query, or header, so a caller authed for tenant A cannot ask for
  tenant B by URL.
- A kit/asset id belonging to another tenant returns **404, not 403** — the fence
  does not leak that another tenant's id exists.
- **No destructive verbs.** The `/v1/brand-kits` surface has **no `PUT` and no
  `DELETE`**. Updates are soft (`PATCH` bumps `version`, updates in place);
  removal is a soft-deactivate (`PATCH {"is_active": false}`), reversible. Brand
  history is append/curate-only. A route-tree test enforces this invariant against
  the live OpenAPI schema.
- Management requires an **authenticated human with a tenant**. `get_current_user`
  rejects Janua service principals (403); the router additionally requires a
  non-null `org_id`.

The one place a `janua_org_id` is accepted from a request body is
`POST /v1/brand-kits/clients` (tenant onboarding) — and it is **admin-only**.

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/v1/brand-kits/clients` | admin | Onboard a tenant: bind a Janua org to a `Client`. |
| `GET` | `/v1/brand-kits/me/client` | tenant | The caller's resolved tenant. |
| `GET` | `/v1/brand-kits` | tenant | List the caller tenant's kits. |
| `POST` | `/v1/brand-kits` | tenant | Create/initialize a kit. |
| `GET` | `/v1/brand-kits/{id}` | tenant | Structured kit (management view). |
| `PATCH` | `/v1/brand-kits/{id}` | tenant | Soft-update structured data (bumps `version`); `is_active:false` soft-deactivates. |
| `POST` | `/v1/brand-kits/{id}/assets` | tenant | Upload a binary brand asset (multipart) → R2. |
| `GET` | `/v1/brand-kits/{id}/assets` | tenant | List a kit's binary assets. |
| `GET` | `/v1/brand-kits/{id}/assets/{assetId}` | tenant | One asset + fresh download URL. |
| `GET` | `/v1/brand-kits/{id}/tokens` | tenant | **Resolved token export — the consumer contract.** |

"tenant" = an authenticated human whose token carries an org provisioned as a
`Client`.

## R2 key layout (tenant-scoped, versioned)

```
brand-kits/{client_slug}/{kit_version}/{kind}/{asset_id}_{filename}
```

The client slug fences tenants apart in the object namespace; the kit version
groups a version's assets; `kind` groups by role; the `asset_id` prefix
guarantees uniqueness. Bytes go through the shared `StorageClient` (same
`ceq-assets` bucket as renders and `/v1/assets`).

## Versioning choice

A `version` integer + soft update, **not** a full per-edit history table. `PATCH`
bumps `version` and updates the structured columns in place; a consumer that must
pin records the `version` it aligned against (surfaced in the token export).
Full append-only history is a deliberate deferral — `version` is the seam a future
`brand_kit_versions` table would hang off without changing the read contract.

## The `/tokens` export contract

`GET /v1/brand-kits/{id}/tokens` returns a resolved, consumer-ready token
document — what MAP, crea-frontend, and ceq's renderer pull to **align on brand**.
It flattens the kit into named palette tokens, typography roles, and logos already
resolved to fetchable URLs, plus a pinnable `version`. No R2 knowledge is required
on the consumer side. A dangling/deactivated logo reference is skipped, not fatal.

```json
{
  "client_slug": "crea-tu-mundo",
  "kit_id": "3f2a…",
  "kit_name": "Primary",
  "version": 3,
  "palette": {
    "brand": "#7C5CFF",
    "accent": "#3CE0C0",
    "ink": {"light": "#0B0B12", "dark": "#F5F5FA"}
  },
  "typography": {
    "heading": {"family": "Space Grotesk", "weights": [500, 700]},
    "body": {"family": "Inter", "weights": [400, 600]}
  },
  "logos": {
    "primary": {
      "asset_id": "9c1e…",
      "kind": "logo-primary",
      "variant": null,
      "content_type": "image/svg+xml",
      "url": "https://…presigned…/brand-kits/crea-tu-mundo/3/logo-primary/…svg"
    }
  },
  "guidelines": {
    "clear_space": "1x cap-height on all sides",
    "min_size_px": 24,
    "tagline": "Crea tu mundo",
    "do": ["Use on dark surfaces"],
    "dont": ["Never recolor the mark"]
  },
  "generated_at": "2026-09-01T00:00:00Z"
}
```

### Contract notes for consumers

- **Address palette tokens by name** (`palette.brand`), not by position. A value is
  either a hex string or a `{light, dark}` object where the token differs by theme.
- **Typography** is keyed by role (`heading` / `body` / `mono`), each with `family`
  and `weights`; an optional `scale` may appear.
- **Logos** are keyed by logical variant (`primary`, `inverse`, `mark`, `wordmark`)
  and already resolved to a fetchable `url`. `url` is a presigned R2 URL (expires);
  fetch on use rather than storing it.
- **Pin on `version`** when an alignment must be reproducible.
