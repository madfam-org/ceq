# CEQ Templates Guide

This guide reflects the templates that are present in this repository as of the
2026-06-01 repo audit. CEQ has two related template surfaces:

- **Workflow JSON files** under `templates/`: checked-in ComfyUI workflow assets.
- **Seeded database templates** in `apps/api/src/ceq_api/seed_templates.py`:
  the 13 records created by `python -m ceq_api.scripts.seed_db`.

The API also has a separate deterministic render-template registry for
`/v1/render/*`; those templates are listed at the end.

## Checked-In Workflow Files

| Path | Category | Notes |
|------|----------|-------|
| `templates/social/flux-schnell.json` | social | FLUX schnell image workflow |
| `templates/social/instantid-portrait.json` | social | InstantID portrait workflow |
| `templates/video/hunyuan-video.json` | video | Hunyuan video workflow |
| `templates/3d/triposr-image-to-3d.json` | 3d | TripoSR image-to-3D workflow |
| `templates/utility/image-upscaler.json` | utility | Image upscale workflow |
| `templates/utility/sdxl-txt2img.json` | utility | SDXL text-to-image workflow |

## Seeded Database Templates

The production seed script currently defines 13 templates:

| Category | Template | VRAM | Primary inputs |
|----------|----------|------|----------------|
| social | FLUX.1 DEV | 24GB | prompt, negative_prompt, width, height, steps, cfg, seed |
| social | FLUX.1 SCHNELL | 16GB | prompt, width, height, seed |
| social | SD3 Medium | 16GB | prompt, negative_prompt, width, height, steps, cfg, seed |
| social | InstantID Portrait | 12GB | face_image, prompt, negative_prompt, ip_adapter_weight, seed |
| video | Hunyuan Video 1.0 | 24GB | prompt, negative_prompt, frames, width, height, steps, cfg, seed |
| video | I2VGen-XL Image to Video | 16GB | image, prompt, frames, fps, seed |
| video | LivePortrait Animals | 8GB | source_image, driving_video, relative_motion |
| 3d | CRM 3D Model Generator | 16GB | image, remove_background, mesh_resolution |
| 3d | Sketch to 3D | 20GB | sketch, prompt, enhance_sketch |
| 3d | LayerDiffusion + TripoSR | 20GB | prompt, negative_prompt, seed |
| utility | APISR 4x Upscale | 8GB | image, scale |
| utility | YoloWorld + SAM Segmentation | 12GB | image, categories, confidence_threshold |
| utility | Differential Diffusion Inpaint | 12GB | image, mask, prompt, negative_prompt, denoise_strength, seed |

Seed with:

```bash
cd apps/api
python -m ceq_api.scripts.seed_db
```

Use `--force` to update existing rows from source definitions:

```bash
python -m ceq_api.scripts.seed_db --force
```

## API Usage

List templates:

```bash
curl https://api.ceq.lol/v1/templates \
  -H "Authorization: Bearer <janua-jwt>"
```

Get a template:

```bash
curl https://api.ceq.lol/v1/templates/<template-id> \
  -H "Authorization: Bearer <janua-jwt>"
```

Fork a template into a workflow:

```bash
curl -X POST https://api.ceq.lol/v1/templates/<template-id>/fork \
  -H "Authorization: Bearer <janua-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Custom Workflow"}'
```

Run a seeded template:

```bash
curl -X POST https://api.ceq.lol/v1/templates/<template-id>/run \
  -H "Authorization: Bearer <janua-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"params": {"prompt": "cosmic nebula"}, "priority": 0}'
```

## Render Templates

The `/v1/render/*` API uses pure renderers registered in
`apps/api/src/ceq_api/render/renderers/`, not the ComfyUI workflow template
catalog.

| Template | Endpoint | Output | Evidence |
|----------|----------|--------|----------|
| `card-standard` | `/v1/render/card`, `/thumbnail` | 512x768 PNG | `CardStandardRenderer` |
| `tone-beep` | `/v1/render/audio` | 16-bit PCM WAV at 22.05kHz | `ToneBeepRenderer` |
| `card-plate` | `/v1/render/3d` | GLB / glTF 2.0 binary | `CardPlateRenderer` |

The render API is deterministic and R2-cached. In production it requires Janua
auth; unauthenticated `/v1/render/card` returned `401` in the 2026-06-01 public
smoke.
