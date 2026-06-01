# Getting Started with CEQ

> *Quantize some chaos*

Welcome to **CEQ** — Creative Entropy Quantized. This guide will help you get started with creating AI-generated content using our streamlined ComfyUI interface.

## What is CEQ?

CEQ is a content generation platform that wraps [ComfyUI](https://github.com/comfyanonymous/ComfyUI) with a clean, hacker-friendly interface. It's designed for power users who want:

- **Full ComfyUI power** when you need it
- **Streamlined templates** for common workflows
- **Keyboard-first UX** for maximum flow
- **Real-time job monitoring** via WebSocket
- **Output publishing API** (currently webhook + selected channels; many social channels remain `coming_soon`)

## Quick Tour

### 1. Templates

Start with pre-built workflows for common tasks:

| Category | Use Cases |
|----------|-----------|
| **Social Media** | Post images, carousels, thumbnails |
| **Video Clone** | Talking heads, lip sync, avatars |
| **3D Render** | Product shots, scenes, textures |
| **Utility** | Upscale, background removal, style transfer |

### 2. Workflow Editor

For custom work, the visual editor gives you:
- Drag-and-drop node composition
- Real-time preview
- Keyboard shortcuts for everything
- Save & version your workflows

### 3. Queue Monitor

Track your jobs in real-time:
- See job status and progress
- Watch progress updates
- Review execution logs
- Retry failed jobs

### 4. Output Gallery

All your generated content in one place:
- Browse by workflow or date
- View metadata and settings
- Publish via the output API (supported surfaces vary by channel)
- Download originals

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd + Enter` | Run workflow |
| `Cmd + K` | Command palette |
| `Cmd + N` | New workflow |
| `Cmd + S` | Save workflow |
| `Cmd + Shift + P` | Publish output |
| `Tab` | Next input |
| `Escape` | Cancel / Close |
| `Space` | Preview fullscreen |

## Your First Generation

1. **Open a template**: Click "Templates" and choose "Social Post"
2. **Configure inputs**: Enter your prompt and adjust settings
3. **Run it**: Press `Cmd + Enter`
4. **Watch the magic**: Monitor progress in real-time
5. **Review & iterate**: Tweak and re-run until perfect
6. **Ship it**: Export outputs or publish via supported channels

## Brand Voice

CEQ has personality. You'll see messages like:

| State | Message |
|-------|---------|
| Loading | "Quantizing entropy..." |
| Processing | "Transmuting latent space..." |
| Success | "Signal acquired." |
| Error | "Chaos won this round. Retry?" |
| Queue | "In the crucible..." |

## GPU Workers

Your workflows run on dedicated GPU instances:

- **Provider-managed scaling**: Worker lifecycle is controlled by configured worker/provider orchestration.
- **Cost control**: Lifecycle policy is provider-specific and managed outside CEQ defaults.
- **Model caching**: Common models are pre-loaded

## Authentication

CEQ uses Janua for authentication. Visit [ceq.lol](https://ceq.lol) for the
public demo/landing experience, then log in to Studio at
[app.ceq.lol](https://app.ceq.lol) with your MADFAM credentials. Studio routes
are protected by CEQ session cookies; unauthenticated visitors are redirected
to Janua through `/login`.

If Janua returns `invalid_client`, treat it as configuration drift: the CEQ
OAuth client is registered in production, and the 2026-06-01 audit verified the
Studio token route is accepted by Janua.

## Need Help?

- **This documentation**: Browse all guides
- **Templates**: Study the pre-built workflows
- **API docs**: See [API Reference](./API.md)

---

*"The terminal awaits. Let's quantize some chaos."* — ceq.lol
