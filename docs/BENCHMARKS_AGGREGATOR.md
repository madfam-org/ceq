# Benchmarks Aggregator — Design Doc

> Studio feature: a best-value / SOTA tracker for open media-generation models.
> Status: **first slice shipped** (hand-curated seed + `/benchmarks` page). The
> auto-refresh job is designed here but **not built**.

Route: `app.ceq.lol/benchmarks` · Nav: sidebar ⌘6 + command palette
Code: `apps/studio/src/lib/benchmarks.ts` (data + scoring),
`apps/studio/src/app/benchmarks/page.tsx` (UI),
`apps/studio/__tests__/lib/benchmarks.test.ts` (tests).

---

## 1. Vision

ceq is a ComfyUI wrapper; its unit of work is "a model run as a ComfyUI graph."
The open media-generation frontier moves monthly, and ceq's checked-in catalog
is already 1–2 generations stale (Hunyuan Video 1.0, TripoSR/CRM). MADFAM needs
a single, always-current answer to: **for each media type, what is the
best-value SOTA open model we can actually run today, and what are its
licensing traps?**

"Best value" here is not "highest quality" — it is the intersection of:

- **capability** (is it SOTA / a standardize-now pick?),
- **commercial-cleanliness** (can MADFAM ship its output?),
- **VRAM-efficiency** (does it fit our cost-capped GPU tiers?),
- **ComfyUI-readiness** (drop-in vs a fragile custom-node build).

The page keeps MADFAM and ceq's users informed of that intersection across all
six modalities (image, video, 3D, multimodal/VLM, audio-TTS, audio-music), with
the **licensing risk flags surfaced prominently** — the single most load-bearing,
easy-to-get-wrong signal in the open-weights space.

## 2. Data source (this slice)

Seeded from the 2026-08-28 ceq model-selection research pass (image/video/3D/VLM
+ audio & efficiency), which is grounded in ceq's actual catalog
(`docs/TEMPLATES.md`) and verified against primary GitHub/HF/comfy.org pages.
**39 models across all six modalities.** Every entry carries a `sourceUrl` and a
`verifiedDate`.

Caveat carried into the UI: speed / VRAM figures are vendor / community numbers
on H100/4090-class hardware and **must be re-measured on ceq's own GPU workers**
in a Phase-0 bake-off — they are directional, not ceq-measured.

## 3. Data model

`apps/studio/src/lib/benchmarks.ts` — pure data + pure functions (no I/O, no
React), so it backs the page today and a refresh job later. One entry per model:

| Field | Type | Notes |
|---|---|---|
| `id`, `name`, `maker` | string | identity |
| `modality` | `image \| video \| 3d \| vlm \| tts \| music` | |
| `license` | string | maker's published license name |
| `licenseClass` | `apache \| mit \| openrail \| non-commercial \| revenue-gated \| geo-gated \| api-only` | the commercial-risk normalization |
| `commercialOk` | boolean | safe for MADFAM's published output |
| `vramGb` | number \| null | fp16/bf16 GB; `null` = CPU-capable |
| `vramNote` | string | quant / offload floor (GGUF/FP8/block-swap) |
| `comfyuiRating` | `drop-in \| custom-node \| needs-build \| api-only` | build risk |
| `speedNote` | string | wall-clock / throughput |
| `bestAt` | string | one-line summary |
| `tier` | `standardize-now \| efficiency-pick \| watch` | editorial verdict |
| `sourceUrl`, `verifiedDate` | string | provenance |
| `riskFlag?` | string | prominent inline warning (geo / revenue / ambiguity) |

### License signal (traffic light)

`licenseSignal(licenseClass)` collapses the class into `green` (apache/mit/openrail —
commercial-clean), `amber` (revenue-gated/geo-gated — usable but gated), `red`
(non-commercial/api-only). This is the color coding on every card's license badge.

### Best-value score

`bestValueScore(model)` → `0..100`, a composite heuristic (not a benchmark):

```
score = tierWeight × licenseWeight × vramEfficiency(vramGb) × comfyWeight  (×100)
```

- `tierWeight`: standardize-now 1.0 · efficiency-pick 0.9 · watch 0.55
- `licenseWeight`: apache/mit 1.0 · openrail 0.9 · revenue/geo-gated 0.6 · non-commercial 0.25 · api-only 0.1
- `vramEfficiency`: 1.0 at ≤8GB, linear falloff to 0.3 at ≥48GB, `null` (CPU) = 1.0
- `comfyWeight`: drop-in 1.0 · custom-node 0.75 · needs-build 0.35 · api-only 0.1

It is an intentionally transparent, tunable ranking signal — used only to order
models within a modality group. The weights are the place to encode MADFAM's
priorities (e.g. raise `licenseWeight`'s penalty if sovereignty tightens).

## 4. The page

Client component mirroring the Studio gallery pattern (`MainLayout`, local
`useState` filtering, `ceq-card` / `Badge` / `Switch`, lucide icons). Models are
grouped by modality (generators first, then VLM, then audio), each group sorted
standardize-now → efficiency-pick → watch, then by best-value score.

Each card shows: name + maker, tier pill (star = standardize-now, lightning =
efficiency-pick), the color-coded license badge, a ComfyUI-rating badge, VRAM,
"best at", VRAM/speed notes, the best-value score, a source link, and — when
present — a prominent amber risk flag.

Interactive controls (client-side, mirroring gallery filtering):

- **Modality** filter buttons (All + one per modality),
- **Commercial-safe only** toggle (`commercialOk`),
- **Runs in ComfyUI** toggle (`runsInComfyUI` — excludes api-only).

standardize-now and efficiency-pick cards are visually distinct (primary /
green borders + pills); watch-tier cards are de-emphasized.

## 5. How the data stays current

**This slice: hand-curated seed.** Facts, `verifiedDate`, and `riskFlag` are
edited in `benchmarks.ts` by a human against primary sources.

**Next: a periodic refresh job (designed, not built).** The mechanism:

1. **Pull candidates** — a scheduled job (Enclii cron / GH Action) queries
   sources: HuggingFace Hub API (trending + task-filtered model cards),
   arena/leaderboard signals (LMArena-style, ComfyUI model indexes), and the
   comfy.org / node-registry to detect a published custom-node pack.
2. **Re-verify the load-bearing facts** — for each tracked/candidate model,
   re-read the primary model card to refresh **license text → `licenseClass`**
   (a regex/keyword classifier over the LICENSE, human-reviewed on change),
   param count / VRAM hints, and ComfyUI node availability. License and VRAM are
   the fields most likely to silently drift and most costly to get wrong.
3. **Diff + gate** — emit a proposed diff to `benchmarks.ts` (or a JSON the
   module imports). **License/tier/commercialOk changes require human approval**
   (open a PR, never auto-merge a licensing reclassification) because a
   misclassified license is a legal liability. Pure metadata refreshes
   (verifiedDate, speed notes) can land more freely.
4. **Re-measure on ceq workers** — speed/VRAM numbers get overwritten by a
   Phase-0 bake-off harness once the GPU golden path is unblocked (currently 0
   replicas), replacing vendor figures with ceq-measured ones.

Design principle: **the aggregator proposes, a human disposes on anything with
legal or standardization weight.** The scraper is a candidate-finder and
fact-refresher, not an autonomous catalog editor.

## 6. Phased roadmap

- **Phase 1 (this slice, done):** typed model + 39-model seed + `/benchmarks`
  page + filters + nav + tests.
- **Phase 2:** move the seed to a versioned JSON with a schema + CI validation;
  add per-model detail view and a compare mode; surface the efficiency toolkit
  (GGUF / Nunchaku / block-swap / step-distill LoRAs) as an orthogonal facet.
- **Phase 3:** the refresh job (§5 steps 1–3) landing PRs; a "changed since you
  last looked" diff feed; wire "adopt" from a card to a template scaffold
  (`docs/TEMPLATES.md` actions — e.g. Wan 2.2 → `wan22-ti2v-5b.json`).
- **Phase 4:** ceq-measured speed/VRAM from the Phase-0 bake-off harness once
  GPU workers are live; a cost-per-render column feeding the best-value score.

## 7. Open questions

- **Refresh cadence & source of truth for leaderboards** — no single open API
  ranks all six modalities; the pull step will be a per-modality adapter set.
- **License classification confidence** — the regex classifier will need a
  human-review queue for ambiguous cases (Sana is the canonical example: Apache
  code repo vs possibly non-commercial NVIDIA weights).
- **Whether to expose the score publicly** — the composite is opinionated; may
  want to show the four component factors rather than a single number to avoid
  false precision.
- **Seed vs JSON** — kept inline in `benchmarks.ts` for this slice; Phase 2
  decides if the volume justifies an external JSON + schema.
