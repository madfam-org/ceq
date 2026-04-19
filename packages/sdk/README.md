# @ceq/sdk

Client SDK for [ceq.lol](https://ceq.lol) — MADFAM's generative asset platform.

Render thumbnails, cards, and (soon) audio/3D assets with deterministic caching. Same inputs always produce the same URL, so it's safe to call on every record save.

## Install

```bash
pnpm add @ceq/sdk
# or
npm install @ceq/sdk
```

## Quick start

```ts
import { CeqClient } from "@ceq/sdk";

const ceq = new CeqClient({
  // Token can be a string or async function (e.g. refreshing Janua token).
  token: async () => await getJanuaAccessToken(),
});

const { url, cached } = await ceq.renderCard({
  title: "Volcán",
  subtitle: "Elemental / Fire",
  description: "A fiery catalyst.",
  accent: "#FF5A3C",
  badge: "SR",
  glyph: "V",
});

// Persist `url` on your record. It's immutable (content-addressed) — safe to cache forever.
await db.card.update({ id, thumbnail_url: url });
```

## Options

| Option | Default | Notes |
|---|---|---|
| `baseUrl` | `https://api.ceq.lol` | Override for staging/local dev. |
| `token` | none | Janua bearer token (string or async fn). |
| `fetch` | `globalThis.fetch` | Pass a custom fetch (e.g. wrapped with tracing/retry). |
| `timeoutMs` | `30000` | Per-request timeout. |

## Methods

- `renderCard(data, { template? })` — render the card-standard template (or a variant).
- `renderThumbnail({ template, data })` — generic thumbnail; caller supplies template name.
- `listTemplates()` — enumerate available templates + versions.

## Error handling

Non-2xx responses throw `CeqApiError` carrying `status` + `detail`.

```ts
import { CeqApiError } from "@ceq/sdk";

try {
  await ceq.renderCard({ title: "" });
} catch (err) {
  if (err instanceof CeqApiError && err.status === 422) {
    // validation error from ceq
  }
  throw err;
}
```

## Determinism

Every render is content-addressed: `hash = sha256(template + data + template_version)`. Identical inputs → identical URLs. The R2 cache means repeated calls (same data) skip the actual render and return instantly (`cached: true`).

When a template's visual output changes, we bump `template_version` so old cached assets aren't served.
