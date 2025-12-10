# CEQ Templates Guide

Pre-built workflow templates for common content generation tasks.

## Template Categories

### Social Media (`templates/social/`)

Templates for generating social media content.

| Template | Description | VRAM |
|----------|-------------|------|
| **Post Generator** | Static image posts with text overlays | 12GB |
| **Carousel Builder** | Multi-image carousel sets | 12GB |
| **Story Creator** | Vertical format (9:16) stories | 12GB |
| **Thumbnail Forge** | Video thumbnails with dynamic text | 12GB |

#### Post Generator

Generate eye-catching social media posts.

**Inputs:**
| Input | Type | Description |
|-------|------|-------------|
| `prompt` | string | What to generate |
| `style` | enum | modern, minimal, bold, retro |
| `aspect_ratio` | enum | 1:1, 4:5, 16:9 |
| `seed` | int | Random seed (-1 for random) |

**Example:**
```json
{
  "prompt": "A futuristic cityscape with neon lights",
  "style": "modern",
  "aspect_ratio": "1:1",
  "seed": -1
}
```

---

### Video Clone (`templates/video/`)

Templates for AI-generated video content.

| Template | Description | VRAM |
|----------|-------------|------|
| **Talking Head** | Generate spokesperson videos | 16GB |
| **Lip Sync** | Audio-to-video lip synchronization | 16GB |
| **Expression Transfer** | Map emotions to faces | 16GB |
| **Avatar Animate** | Animate still images | 16GB |

#### Talking Head

Create AI spokesperson videos from a source image and audio.

**Inputs:**
| Input | Type | Description |
|-------|------|-------------|
| `source_image` | file | Reference face image |
| `audio_file` | file | Speech audio (MP3/WAV) |
| `expression` | enum | neutral, happy, serious, excited |
| `movement` | float | Head movement intensity (0-1) |

**Requirements:**
- Source image: Clear face, front-facing, neutral expression
- Audio: Clean speech, minimal background noise
- VRAM: 16GB minimum

---

### 3D Rendering (`templates/3d/`)

Templates for 3D content generation.

| Template | Description | VRAM |
|----------|-------------|------|
| **Product Render** | E-commerce product shots | 18GB |
| **Scene Builder** | Environmental rendering | 18GB |
| **Texture Gen** | Material/texture generation | 12GB |
| **Multiview Gen** | Multi-angle generation | 18GB |

#### Product Render

Generate professional product photography.

**Inputs:**
| Input | Type | Description |
|-------|------|-------------|
| `product_image` | file | Product on white/transparent background |
| `environment` | enum | studio, outdoor, lifestyle, minimal |
| `lighting` | enum | soft, dramatic, natural, product |
| `angle_count` | int | Number of angles (1-8) |

---

### Utility (`templates/utility/`)

Helper templates for post-processing and enhancement.

| Template | Description | VRAM |
|----------|-------------|------|
| **Upscale Enhance** | Resolution enhancement (4x) | 8GB |
| **Background Remove** | Subject isolation with alpha | 8GB |
| **Style Transfer** | Apply artistic styles | 12GB |
| **Batch Process** | Apply workflow to multiple inputs | varies |

#### Upscale Enhance

Increase image resolution with AI enhancement.

**Inputs:**
| Input | Type | Description |
|-------|------|-------------|
| `image` | file | Input image |
| `scale` | enum | 2x, 4x |
| `denoise` | float | Noise reduction (0-1) |
| `face_enhance` | bool | Enable face restoration |

---

## Using Templates

### From the UI

1. Click **Templates** in the sidebar
2. Browse by category
3. Click a template to open it
4. Configure your inputs
5. Press `Cmd + Enter` to run

### From the API

```bash
# Fork a template to create your own workflow
curl -X POST https://api.ceq.lol/v1/templates/{id}/fork \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Custom Workflow"}'
```

### From the SDK

```python
from ceq import CEQClient

client = CEQClient(token="...")

# List templates
templates = client.templates.list(category="social")

# Fork a template
workflow = client.templates.fork(
    template_id="post-generator",
    name="My Social Posts"
)

# Run with custom params
job = workflow.run(params={
    "prompt": "cosmic nebula",
    "style": "modern"
})
```

---

## Custom Templates

Create your own templates from existing workflows:

1. Create and test your workflow
2. Define an input schema (JSON Schema)
3. Save as template (admin only)

### Input Schema Example

```json
{
  "type": "object",
  "properties": {
    "prompt": {
      "type": "string",
      "title": "Prompt",
      "description": "What to generate"
    },
    "style": {
      "type": "string",
      "title": "Style",
      "enum": ["modern", "minimal", "bold", "retro"],
      "default": "modern"
    },
    "seed": {
      "type": "integer",
      "title": "Seed",
      "minimum": -1,
      "default": -1
    }
  },
  "required": ["prompt"]
}
```

---

## Model Requirements

Templates specify which models they need:

| Model | Size | Templates |
|-------|------|-----------|
| SDXL Base | 6.5GB | Social, Utility |
| Flux Dev | 23GB | Social (high quality) |
| WAN 2.1 | 8GB | Video Clone |
| LivePortrait | 4GB | Video Clone |
| Hunyuan 3D | 12GB | 3D Rendering |
| RealESRGAN | 500MB | Upscaling |

Models are automatically downloaded and cached on GPU workers.

---

## Performance Tips

1. **Use the right template**: Don't over-engineer simple tasks
2. **Start with defaults**: Tune settings after initial test
3. **Batch similar jobs**: More efficient than one-at-a-time
4. **Use seeds**: Reproducible results for iteration
5. **Check VRAM**: Some templates need 18GB+ GPUs

---

*For template contributions, see the [developer guide](./CONTRIBUTING.md).*
