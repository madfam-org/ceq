/**
 * Benchmarks Aggregator — seed dataset + types + scoring.
 *
 * A curated, hand-verified snapshot of the best-value, SOTA open / open-weights
 * media-generation models MADFAM tracks for ceq (a ComfyUI wrapper). The goal is
 * a living "best value" tracker across every media-generation modality: which
 * models are advanced AND efficient AND actually runnable in ComfyUI today,
 * with the licensing traps surfaced as a first-class signal.
 *
 * Provenance: seeded from the 2026-08-28 ceq model-selection research pass
 * (docs/BENCHMARKS_AGGREGATOR.md §data-source). Speed/VRAM figures are
 * vendor/community numbers on H100/4090-class hardware and must be re-measured
 * on ceq's own GPU workers — treat as directional, not ceq-measured.
 *
 * This module is intentionally pure data + pure functions (no I/O, no React) so
 * it can back the /benchmarks page today and a periodic refresh job later.
 */

export type Modality = "image" | "video" | "3d" | "vlm" | "tts" | "music";

/**
 * License family, normalized to the commercial-risk classes MADFAM cares about.
 * This is the load-bearing signal: "open" means very different things per release.
 */
export type LicenseClass =
  | "apache" // Apache-2.0 — commercial-clean, no thresholds
  | "mit" // MIT — commercial-clean, no thresholds
  | "openrail" // OpenRAIL / OpenRAIL++-M — commercial with use-based restrictions, no revenue gate
  | "non-commercial" // explicitly non-commercial (FLUX dev, XTTS CPML, etc.)
  | "revenue-gated" // free below a revenue threshold (Stability $1M, LTX $10M)
  | "geo-gated" // territory / MAU carve-outs (Tencent community: excludes EU/UK/SK)
  | "api-only"; // closed weights, not self-hostable — off-limits for ceq

/**
 * How ready the model is to run as a ComfyUI workflow graph — ceq's unit of work.
 */
export type ComfyRating =
  | "drop-in" // runs on core / native nodes, minimal build risk
  | "custom-node" // a published custom-node pack exists (install/build effort)
  | "needs-build" // no production ComfyUI path; MADFAM would build integration
  | "api-only"; // not self-hostable

/**
 * Editorial tier from the research pass.
 * - standardize-now: adopt as a default lane (advanced + efficient + ComfyUI-ready)
 * - efficiency-pick: the best value / VRAM sweet spot within its modality
 * - watch: promising, adopt once it matures (ecosystem / node / weights not ready)
 */
export type Tier = "standardize-now" | "efficiency-pick" | "watch";

export interface BenchmarkModel {
  id: string;
  name: string;
  maker: string;
  modality: Modality;
  /** Human-readable license name as published by the maker. */
  license: string;
  licenseClass: LicenseClass;
  /** True only for licenses safe for MADFAM's commercial / published output. */
  commercialOk: boolean;
  /** fp16/bf16 VRAM footprint in GB (approx). null = not applicable / CPU-capable. */
  vramGb: number | null;
  /** Quantization / offload note — how low the footprint goes in practice. */
  vramNote: string;
  comfyuiRating: ComfyRating;
  /** Speed / throughput note (wall-clock, re-measure on ceq workers). */
  speedNote: string;
  /** One-line "best at" summary. */
  bestAt: string;
  tier: Tier;
  sourceUrl: string;
  /** ISO date the fact was last verified against a primary source. */
  verifiedDate: string;
  /** Optional risk flag surfaced prominently in the UI (geo/revenue/ambiguous). */
  riskFlag?: string;
}

export const MODALITY_LABELS: Record<Modality, string> = {
  image: "Image",
  video: "Video",
  "3d": "3D",
  vlm: "Multimodal / VLM",
  tts: "Audio / TTS",
  music: "Audio / Music",
};

export const LICENSE_CLASS_LABELS: Record<LicenseClass, string> = {
  apache: "Apache-2.0",
  mit: "MIT",
  openrail: "OpenRAIL",
  "non-commercial": "Non-commercial",
  "revenue-gated": "Revenue-gated",
  "geo-gated": "Geo / MAU-gated",
  "api-only": "API-only",
};

export const COMFY_RATING_LABELS: Record<ComfyRating, string> = {
  "drop-in": "Drop-in",
  "custom-node": "Custom node",
  "needs-build": "Needs build",
  "api-only": "API-only",
};

export const TIER_LABELS: Record<Tier, string> = {
  "standardize-now": "Standardize now",
  "efficiency-pick": "Efficiency sweet spot",
  watch: "Watch / next",
};

/**
 * Traffic-light class for a license: green = commercial-clean, amber = usable
 * but gated, red = non-commercial or not self-hostable.
 */
export type LicenseSignal = "green" | "amber" | "red";

export function licenseSignal(licenseClass: LicenseClass): LicenseSignal {
  switch (licenseClass) {
    case "apache":
    case "mit":
    case "openrail":
      return "green";
    case "revenue-gated":
    case "geo-gated":
      return "amber";
    case "non-commercial":
    case "api-only":
      return "red";
  }
}

/** True if the model can run as a ComfyUI graph on ceq workers at all. */
export function runsInComfyUI(model: BenchmarkModel): boolean {
  return model.comfyuiRating !== "api-only";
}

// ---------------------------------------------------------------------------
// "Best value" composite score
// ---------------------------------------------------------------------------

const TIER_WEIGHT: Record<Tier, number> = {
  "standardize-now": 1,
  "efficiency-pick": 0.9,
  watch: 0.55,
};

const LICENSE_WEIGHT: Record<LicenseClass, number> = {
  apache: 1,
  mit: 1,
  openrail: 0.9,
  "revenue-gated": 0.6,
  "geo-gated": 0.6,
  "non-commercial": 0.25,
  "api-only": 0.1,
};

const COMFY_WEIGHT: Record<ComfyRating, number> = {
  "drop-in": 1,
  "custom-node": 0.75,
  "needs-build": 0.35,
  "api-only": 0.1,
};

/**
 * VRAM-efficiency factor in [0.3, 1]: lower VRAM scores higher. CPU-capable /
 * unknown (null) is treated as maximally efficient.
 */
export function vramEfficiency(vramGb: number | null): number {
  if (vramGb == null) return 1;
  if (vramGb <= 8) return 1;
  if (vramGb >= 48) return 0.3;
  // linear falloff between 8GB (1.0) and 48GB (0.3)
  return 1 - ((vramGb - 8) / (48 - 8)) * 0.7;
}

/**
 * Composite "best value" score in [0, 100]: capability tier ×
 * commercial-cleanliness × VRAM-efficiency × ComfyUI-readiness.
 * A heuristic ranking signal, not a benchmark measurement.
 */
export function bestValueScore(model: BenchmarkModel): number {
  const raw =
    TIER_WEIGHT[model.tier] *
    LICENSE_WEIGHT[model.licenseClass] *
    vramEfficiency(model.vramGb) *
    COMFY_WEIGHT[model.comfyuiRating];
  return Math.round(raw * 100);
}

// ---------------------------------------------------------------------------
// Seed dataset (2026-08-28 research pass)
// ---------------------------------------------------------------------------

export const BENCHMARK_MODELS: BenchmarkModel[] = [
  // ---- IMAGE ----
  {
    id: "flux1-schnell",
    name: "FLUX.1 [schnell]",
    maker: "Black Forest Labs",
    modality: "image",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 12,
    vramNote: "GGUF/FP8 to ~8-12GB; 12B params",
    comfyuiRating: "drop-in",
    speedNote: "4-step base; ceq's current pictogram golden path",
    bestAt: "Fast clean-license base; proven fallback",
    tier: "standardize-now",
    sourceUrl: "https://huggingface.co/black-forest-labs/FLUX.1-schnell",
    verifiedDate: "2026-08-28",
  },
  {
    id: "z-image-turbo",
    name: "Z-Image-Turbo",
    maker: "Alibaba Tongyi-MAI",
    modality: "image",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 14,
    vramNote: "BF16 ~14-16GB / FP8 ~8GB / GGUF ~6GB",
    comfyuiRating: "drop-in",
    speedNote: "6B DiT, ~8 steps, ~2-3s/1024² on a 4090",
    bestAt: "Efficiency sweet spot: strong adherence, best speed-per-worker",
    tier: "efficiency-pick",
    sourceUrl: "https://nunchaku.tech/docs/nunchaku/usage/zimage.html",
    verifiedDate: "2026-08-28",
  },
  {
    id: "sdxl",
    name: "SDXL (+ DMD2 / Lightning)",
    maker: "Stability AI + distillers",
    modality: "image",
    license: "OpenRAIL++-M (base; distills vary)",
    licenseClass: "openrail",
    commercialOk: true,
    vramGb: 8,
    vramNote: "~6-8GB fp16; 1-8 step distill LoRAs",
    comfyuiRating: "drop-in",
    speedNote: "1-8 steps via Lightning/Hyper-SD/DMD2/LCM",
    bestAt: "Deepest LoRA/ControlNet ecosystem — pictogram workhorse",
    tier: "standardize-now",
    sourceUrl: "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0",
    verifiedDate: "2026-08-28",
    riskFlag: "Each distill checkpoint carries its own license — verify per-checkpoint.",
  },
  {
    id: "qwen-image",
    name: "Qwen-Image / Qwen-Image-Edit",
    maker: "Alibaba",
    modality: "image",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 40,
    vramNote: "BF16 ≥40GB / FP8 ~16GB / GGUF Q4 ~14GB / Q2 ~8GB",
    comfyuiRating: "drop-in",
    speedNote: "20B; native + GGUF + Nunchaku",
    bestAt: "Best text-in-image, best prompt adherence, 3-ref edit",
    tier: "standardize-now",
    sourceUrl: "https://github.com/QwenLM/Qwen-Image",
    verifiedDate: "2026-08-28",
  },
  {
    id: "flux2-klein-4b",
    name: "FLUX.2 [klein-4B]",
    maker: "Black Forest Labs",
    modality: "image",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 8,
    vramNote: "~8.4GB distilled",
    comfyuiRating: "drop-in",
    speedNote: "Distilled 4-step, ~1.2s (5090); unified gen+edit",
    bestAt: "Newest Apache DiT; adopt once LoRA/ControlNet ecosystem matures",
    tier: "watch",
    sourceUrl: "https://huggingface.co/black-forest-labs/FLUX.2-klein-4B",
    verifiedDate: "2026-08-28",
  },
  {
    id: "flux2-dev",
    name: "FLUX.2 [dev]",
    maker: "Black Forest Labs",
    modality: "image",
    license: "FLUX Non-Commercial",
    licenseClass: "non-commercial",
    commercialOk: false,
    vramGb: 32,
    vramNote: "32B; GGUF/FP8 lowers footprint",
    comfyuiRating: "custom-node",
    speedNote: "Native day-0 support",
    bestAt: "Best-in-class open image + multi-ref edit — but non-commercial",
    tier: "watch",
    sourceUrl: "https://huggingface.co/black-forest-labs/FLUX.2-dev",
    verifiedDate: "2026-08-28",
    riskFlag: "Non-commercial. Needs a paid BFL license for published/commercial output.",
  },
  {
    id: "sd35-large",
    name: "SD3.5 Large / Turbo / Medium",
    maker: "Stability AI",
    modality: "image",
    license: "Stability Community (<$1M rev)",
    licenseClass: "revenue-gated",
    commercialOk: true,
    vramGb: 8,
    vramNote: "Medium ~6GB; Large heavier",
    comfyuiRating: "drop-in",
    speedNote: "Turbo = 4-step",
    bestAt: "Solid general base — but $1M/yr org-revenue threshold",
    tier: "watch",
    sourceUrl: "https://stability.ai/news-updates/license-update",
    verifiedDate: "2026-08-28",
    riskFlag: "Stability Community License: free only below $1M/yr org revenue.",
  },
  {
    id: "sana-sprint",
    name: "Sana / Sana-Sprint",
    maker: "NVIDIA + MIT",
    modality: "image",
    license: "DISPUTED (Apache code vs NVIDIA non-commercial weights?)",
    licenseClass: "non-commercial",
    commercialOk: false,
    vramGb: 8,
    vramNote: "0.6B/1.6B, linear-attention, low VRAM",
    comfyuiRating: "custom-node",
    speedNote: "Fastest raw (~0.3s, 1-step)",
    bestAt: "Fastest raw image — but license genuinely ambiguous",
    tier: "watch",
    sourceUrl: "https://github.com/NVlabs/Sana/blob/main/LICENSE",
    verifiedDate: "2026-08-28",
    riskFlag: "Biggest landmine: code Apache but weights may be NVIDIA non-commercial. Read the exact weights LICENSE before any commercial use.",
  },
  {
    id: "chroma",
    name: "Chroma",
    maker: "lodestones",
    modality: "image",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 12,
    vramNote: "~8.9B; GGUF lowers footprint",
    comfyuiRating: "custom-node",
    speedNote: "FLUX-schnell-derived",
    bestAt: "Fully-open FLUX-derived base",
    tier: "watch",
    sourceUrl: "https://huggingface.co/lodestones/Chroma",
    verifiedDate: "2026-08-28",
  },

  // ---- VIDEO ----
  {
    id: "wan22-ti2v-5b",
    name: "Wan 2.2 (TI2V-5B)",
    maker: "Alibaba / Wan-AI",
    modality: "video",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 8,
    vramNote: "5B fits 8GB with native offloading; fp8 floor",
    comfyuiRating: "drop-in",
    speedNote: "5s 720P <9min on one consumer GPU; +LightX2V 4-step ≈ 1-3min",
    bestAt: "Efficiency sweet spot: cleanest license + native + 8GB fit",
    tier: "efficiency-pick",
    sourceUrl: "https://docs.comfy.org/tutorials/video/wan/wan2_2",
    verifiedDate: "2026-08-28",
  },
  {
    id: "wan22-i2v-a14b",
    name: "Wan 2.2 (I2V-A14B)",
    maker: "Alibaba / Wan-AI",
    modality: "video",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 16,
    vramNote: "14B MoE runs ~16GB via block-swap (KJNodes)",
    comfyuiRating: "drop-in",
    speedNote: "LightX2V distill: ~40-50min → ~1-3min (480p/5s, ~20×)",
    bestAt: "Best open photorealism/faces; quality tier of the Apache leader",
    tier: "standardize-now",
    sourceUrl: "https://github.com/Wan-Video/Wan2.2",
    verifiedDate: "2026-08-28",
  },
  {
    id: "hunyuanvideo-1-5",
    name: "HunyuanVideo-1.5",
    maker: "Tencent",
    modality: "video",
    license: "Tencent Community (excl. EU/UK/SK, 100M-MAU cap)",
    licenseClass: "geo-gated",
    commercialOk: true,
    vramGb: 14,
    vramNote: "14GB floor with offloading; fp8 is the practical floor",
    comfyuiRating: "drop-in",
    speedNote: "~75s/clip (4090); T2V+I2V+1080p-SR native",
    bestAt: "T2V+I2V in one 8.3B model, best faces — gate EU/UK/SK users",
    tier: "standardize-now",
    sourceUrl: "https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5",
    verifiedDate: "2026-08-28",
    riskFlag: "Excludes EU/UK/South Korea + 100M-MAU cap. Gate those territories, or run LTX-2.5 co-primary instead. Low-bit GGUF degrades badly — fp8 floor.",
  },
  {
    id: "ltx-2-5",
    name: "LTX-2.5",
    maker: "Lightricks",
    modality: "video",
    license: "LTX-2 Community (free <$10M rev)",
    licenseClass: "revenue-gated",
    commercialOk: true,
    vramGb: 22,
    vramNote: "22B DiT ~20-22.7GiB (int8); 5s-clip ceiling on 24GB",
    comfyuiRating: "drop-in",
    speedNote: "Distilled fixed 8-step, ~18× faster than Wan 14B",
    bestAt: "Only open model with native synced audio+video; fastest drafts",
    tier: "standardize-now",
    sourceUrl: "https://huggingface.co/Lightricks/LTX-2.5",
    verifiedDate: "2026-08-28",
    riskFlag: "$10M/yr revenue threshold — a future liability. 10s clips can OOM at VAE decode on 24GB.",
  },
  {
    id: "wan22-s2v",
    name: "Wan2.2-S2V-14B",
    maker: "Alibaba",
    modality: "video",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 16,
    vramNote: "14B; block-swap to ~16GB",
    comfyuiRating: "drop-in",
    speedNote: "Native ComfyUI",
    bestAt: "Speech-to-video / talking-head avatar (clean license)",
    tier: "standardize-now",
    sourceUrl: "https://huggingface.co/Wan-AI",
    verifiedDate: "2026-08-28",
  },
  {
    id: "framepack",
    name: "FramePack",
    maker: "lllyasviel",
    modality: "video",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 6,
    vramNote: "6GB floor (Hunyuan-13B I2V base)",
    comfyuiRating: "custom-node",
    speedNote: "60s+ anti-drift long video",
    bestAt: "Lowest-VRAM long-form; accept wrapper-maturity risk",
    tier: "efficiency-pick",
    sourceUrl: "https://github.com/lllyasviel/FramePack",
    verifiedDate: "2026-08-28",
    riskFlag: "kijai wrapper may be stale — verify commit log before depending on it.",
  },
  {
    id: "magi-1-1",
    name: "MAGI-1.1 (4.5B / 24B)",
    maker: "Sand AI",
    modality: "video",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 24,
    vramNote: "4.5B on 1×4090",
    comfyuiRating: "custom-node",
    speedNote: "Autoregressive / streaming long-form",
    bestAt: "Streaming long-form video (watch: newest Apache entrant)",
    tier: "watch",
    sourceUrl: "https://github.com/SandAI-org/MAGI-1",
    verifiedDate: "2026-08-28",
  },

  // ---- 3D ----
  {
    id: "trellis-2",
    name: "TRELLIS.2 (4B)",
    maker: "Microsoft",
    modality: "3d",
    license: "MIT",
    licenseClass: "mit",
    commercialOk: true,
    vramGb: 24,
    vramNote: "min 24GB; FP8 lowers VRAM; 1536³ hero wants 40-80GB",
    comfyuiRating: "custom-node",
    speedNote: "H100 ~3s@512³ / ~17s@1024³ / ~60s@1536³",
    bestAt: "Image-to-3D default: complex topology + one-pass PBR, MIT-clean",
    tier: "standardize-now",
    sourceUrl: "https://github.com/microsoft/TRELLIS.2",
    verifiedDate: "2026-08-28",
    riskFlag: "ComfyUI-Trellis2 needs pre-built wheels — pin a Docker image, never trust 3D-Pack auto-installer.",
  },
  {
    id: "triposg",
    name: "TripoSG (1B)",
    maker: "VAST AI",
    modality: "3d",
    license: "MIT",
    licenseClass: "mit",
    commercialOk: true,
    vramGb: 8,
    vramNote: ">8GB, fast",
    comfyuiRating: "drop-in",
    speedNote: "Fast; lowest install friction of any modern 3D model",
    bestAt: "Efficiency sweet spot: shape-only geometry, cleanest install, MIT",
    tier: "efficiency-pick",
    sourceUrl: "https://huggingface.co/VAST-AI/TripoSG",
    verifiedDate: "2026-08-28",
  },
  {
    id: "hunyuan3d-2-1",
    name: "Hunyuan3D-2.1 (Shape + Paint)",
    maker: "Tencent",
    modality: "3d",
    license: "Tencent Community (<1M MAU, excl. EU/UK/SK)",
    licenseClass: "geo-gated",
    commercialOk: true,
    vramGb: 29,
    vramNote: "Shape ~10GB, Texture ~21GB, combined ~29GB fp16; FP8 halves it",
    comfyuiRating: "custom-node",
    speedNote: "Texture pass ~30min/4090 at full settings (cost-cap risk)",
    bestAt: "Best open PBR texture (4K/8K), text-to-3D + poly control",
    tier: "standardize-now",
    sourceUrl: "https://huggingface.co/tencent/Hunyuan3D-2.1",
    verifiedDate: "2026-08-28",
    riskFlag: "<1M MAU + excludes EU/UK/South Korea. Gate behind a license check; don't distribute weights into those territories.",
  },
  {
    id: "hunyuan3d-paint-2-1",
    name: "Hunyuan3D-Paint-v2-1 (2B)",
    maker: "Tencent",
    modality: "3d",
    license: "Tencent Community",
    licenseClass: "geo-gated",
    commercialOk: true,
    vramGb: 21,
    vramNote: "Texture pass; FP8 lowers footprint",
    comfyuiRating: "custom-node",
    speedNote: "Mesh-conditioned, view-consistent",
    bestAt: "Best open mesh-conditioned PBR texturing (paints onto geometry)",
    tier: "standardize-now",
    sourceUrl: "https://github.com/kijai/ComfyUI-Hunyuan3DWrapper",
    verifiedDate: "2026-08-28",
    riskFlag: "Tencent community carve-outs (EU/UK/SK, MAU cap). Rasterizer compile required.",
  },
  {
    id: "sf3d",
    name: "SF3D / Stable-Fast-3D",
    maker: "Stability AI",
    modality: "3d",
    license: "Stability Community (>$1M rev)",
    licenseClass: "revenue-gated",
    commercialOk: true,
    vramGb: 8,
    vramNote: "Fast textured mesh",
    comfyuiRating: "custom-node",
    speedNote: "~0.5s ultra-fast",
    bestAt: "Ultra-fast textured mesh — but $1M revenue threshold",
    tier: "watch",
    sourceUrl: "https://huggingface.co/stabilityai/stable-fast-3d",
    verifiedDate: "2026-08-28",
    riskFlag: "$1M/yr revenue threshold makes it non-sovereign for MADFAM. Prefer TripoSG (MIT).",
  },
  {
    id: "meshanything-v2",
    name: "MeshAnything V2",
    maker: "ICCV 2025",
    modality: "3d",
    license: "MIT",
    licenseClass: "mit",
    commercialOk: true,
    vramGb: 16,
    vramNote: "Research code",
    comfyuiRating: "needs-build",
    speedNote: "Artist-quality topology / retopo",
    bestAt: "Mesh topology / retopology (research code — no production node)",
    tier: "watch",
    sourceUrl: "https://github.com/buaacyw/MeshAnythingV2",
    verifiedDate: "2026-08-28",
  },

  // ---- MULTIMODAL / VLM ----
  {
    id: "florence-2",
    name: "Florence-2",
    maker: "Microsoft",
    modality: "vlm",
    license: "MIT",
    licenseClass: "mit",
    commercialOk: true,
    vramGb: 1,
    vramNote: "0.23B/0.77B, ~1GB VRAM",
    comfyuiRating: "drop-in",
    speedNote: "Tiny + fast; most mature VLM node (~1.6M downloads)",
    bestAt: "Efficiency sweet spot: captioning, detection, OCR — in-graph",
    tier: "efficiency-pick",
    sourceUrl: "https://github.com/kijai/ComfyUI-Florence2",
    verifiedDate: "2026-08-28",
  },
  {
    id: "florence-2-promptgen",
    name: "Florence-2-PromptGen v2.0",
    maker: "MiaoshouAI",
    modality: "vlm",
    license: "MIT",
    licenseClass: "mit",
    commercialOk: true,
    vramGb: 1,
    vramNote: "~1GB VRAM",
    comfyuiRating: "drop-in",
    speedNote: "Adds tag/caption/analyze modes",
    bestAt: "Pictogram QA backbone: 'clean single icon' composition checks",
    tier: "standardize-now",
    sourceUrl: "https://huggingface.co/MiaoshouAI/Florence-2-large-PromptGen-v2.0",
    verifiedDate: "2026-08-28",
  },
  {
    id: "qwen3-vl",
    name: "Qwen3-VL (2B/4B/8B/32B)",
    maker: "Alibaba",
    modality: "vlm",
    license: "Apache-2.0 (small/mid dense)",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 12,
    vramNote: "8B at Q8 ≈ <12GB; GGUF + native",
    comfyuiRating: "custom-node",
    speedNote: "Native GGUF via ComfyUI-QwenVL",
    bestAt: "Best all-round VLM: OCR (32 lang), grounding/bbox, reasoning",
    tier: "standardize-now",
    sourceUrl: "https://github.com/1038lab/ComfyUI-QwenVL",
    verifiedDate: "2026-08-28",
  },
  {
    id: "wd14-tagger",
    name: "WD14 v3 taggers",
    maker: "SmilingWolf",
    modality: "vlm",
    license: "Open",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 2,
    vramNote: "Tiny ONNX <2GB",
    comfyuiRating: "drop-in",
    speedNote: "Very fast ONNX",
    bestAt: "Booru-style tag interrogation for cheap QA sanity checks",
    tier: "standardize-now",
    sourceUrl: "https://github.com/pythongosssss/ComfyUI-WD14-Tagger",
    verifiedDate: "2026-08-28",
  },
  {
    id: "internvl3-5",
    name: "InternVL3.5 (4B/8B)",
    maker: "OpenGVLab",
    modality: "vlm",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 16,
    vramNote: "Often run from an external inference server",
    comfyuiRating: "custom-node",
    speedNote: "Benchmark-edge perception + reasoning",
    bestAt: "SOTA open perception+reasoning (less turnkey — often external server)",
    tier: "watch",
    sourceUrl: "https://arxiv.org/abs/2508.18265",
    verifiedDate: "2026-08-28",
  },
  {
    id: "minicpm-v-4-5",
    name: "MiniCPM-V 4.5 (8B)",
    maker: "OpenBMB",
    modality: "vlm",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 8,
    vramNote: "~6-8GB Q4",
    comfyuiRating: "custom-node",
    speedNote: "Efficient; GGUF / Ollama",
    bestAt: "Leads OCRBench; efficient OCR-heavy VLM",
    tier: "watch",
    sourceUrl: "https://huggingface.co/openbmb/MiniCPM-V-4_5",
    verifiedDate: "2026-08-28",
  },
  {
    id: "emu3-5",
    name: "Emu3.5",
    maker: "BAAI",
    modality: "vlm",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 40,
    vramNote: "HF weights live; no mature node yet",
    comfyuiRating: "needs-build",
    speedNote: "10T-token any-to-image world model",
    bestAt: "First plausible unified generate+understand candidate (not production-ready)",
    tier: "watch",
    sourceUrl: "https://huggingface.co/BAAI/Emu3.5-Image",
    verifiedDate: "2026-08-28",
    riskFlag: "Research-stage. Do NOT route production generation through a unified model in 2026.",
  },

  // ---- AUDIO / TTS ----
  {
    id: "kokoro-82m",
    name: "Kokoro-82M",
    maker: "hexgrad",
    modality: "tts",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: null,
    vramNote: "82M params, CPU-capable (<1GB weights), RTF ~0.5 CPU",
    comfyuiRating: "custom-node",
    speedNote: "Very fast; maps onto ceq's existing CPU WAV lane",
    bestAt: "Efficiency sweet spot: bilingual EN+ES TTS with no GPU needed",
    tier: "efficiency-pick",
    sourceUrl: "https://huggingface.co/hexgrad/Kokoro-82M",
    verifiedDate: "2026-08-28",
    riskFlag: "3 Spanish voices are espeak-driven / ungraded — do not market as production Spanish.",
  },
  {
    id: "chatterbox-ml-v3",
    name: "Chatterbox Multilingual v3",
    maker: "Resemble AI",
    modality: "tts",
    license: "MIT",
    licenseClass: "mit",
    commercialOk: true,
    vramGb: 8,
    vramNote: "GPU; part of TTS-Audio-Suite pack",
    comfyuiRating: "custom-node",
    speedNote: "Zero-shot voice clone from 5s; 23-25 langs",
    bestAt: "Strongest commercial TTS treating Spanish as first-class",
    tier: "standardize-now",
    sourceUrl: "https://github.com/resemble-ai/chatterbox",
    verifiedDate: "2026-08-28",
    riskFlag: "PerTh watermark embedded on every self-hosted output by default — confirm acceptable for Voxa.",
  },
  {
    id: "zonos",
    name: "Zonos-v0.1 / ZONOS2",
    maker: "Zyphra",
    modality: "tts",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 8,
    vramNote: "GPU",
    comfyuiRating: "custom-node",
    speedNote: "Expressive multilingual",
    bestAt: "Commercial-safe cloning fallback if Chatterbox watermark blocks",
    tier: "watch",
    sourceUrl: "https://huggingface.co/Zyphra/Zonos-v0.1-transformer",
    verifiedDate: "2026-08-28",
  },
  {
    id: "xtts-v2",
    name: "XTTS-v2",
    maker: "Coqui",
    modality: "tts",
    license: "CPML (non-commercial)",
    licenseClass: "non-commercial",
    commercialOk: false,
    vramGb: 8,
    vramNote: "GPU; voice cloning",
    comfyuiRating: "custom-node",
    speedNote: "Multilingual incl. ES",
    bestAt: "Voice cloning — but non-commercial and company defunct",
    tier: "watch",
    sourceUrl: "https://huggingface.co/coqui/XTTS-v2",
    verifiedDate: "2026-08-28",
    riskFlag: "Coqui CPML is non-commercial and the company is defunct — no one can sell a license. Avoid for production.",
  },

  // ---- AUDIO / MUSIC ----
  {
    id: "ace-step",
    name: "ACE-Step",
    maker: "ACE Studio + StepFun",
    modality: "music",
    license: "Apache-2.0",
    licenseClass: "apache",
    commercialOk: true,
    vramGb: 8,
    vramNote: "GPU; native in ComfyUI core",
    comfyuiRating: "drop-in",
    speedNote: "v1.5 <2s/song (A100), ~10s (3090)",
    bestAt: "Standardize-now music: Apache, no watermark, ES+EN lyrics, native",
    tier: "standardize-now",
    sourceUrl: "https://github.com/comfyanonymous/ComfyUI",
    verifiedDate: "2026-08-28",
  },
  {
    id: "stable-audio-open",
    name: "Stable Audio Open",
    maker: "Stability AI",
    modality: "music",
    license: "Stability Community (revenue cap)",
    licenseClass: "revenue-gated",
    commercialOk: true,
    vramGb: 8,
    vramNote: "GPU",
    comfyuiRating: "custom-node",
    speedNote: "SFX + short music",
    bestAt: "SFX / short music — but revenue-capped, not strictly OSS",
    tier: "watch",
    sourceUrl: "https://huggingface.co/stabilityai/stable-audio-open-1.0",
    verifiedDate: "2026-08-28",
    riskFlag: "Stability revenue cap; prefer ACE-Step (Apache, no gate).",
  },
  {
    id: "musicgen",
    name: "MusicGen / AudioGen",
    maker: "Meta",
    modality: "music",
    license: "CC-BY-NC (non-commercial)",
    licenseClass: "non-commercial",
    commercialOk: false,
    vramGb: 8,
    vramNote: "GPU",
    comfyuiRating: "custom-node",
    speedNote: "Text-to-music",
    bestAt: "Text-to-music — but CC-BY-NC blocks commercial use",
    tier: "watch",
    sourceUrl: "https://huggingface.co/facebook/musicgen-large",
    verifiedDate: "2026-08-28",
    riskFlag: "CC-BY-NC is non-commercial. Prefer ACE-Step for any published output.",
  },
];

/** Modality display order for the page (generators first, then understanding, then audio). */
export const MODALITY_ORDER: Modality[] = [
  "image",
  "video",
  "3d",
  "vlm",
  "tts",
  "music",
];

export interface ModalityGroup {
  modality: Modality;
  label: string;
  models: BenchmarkModel[];
}

/**
 * Group models by modality (in MODALITY_ORDER), each group sorted by tier then
 * best-value score. Pure — takes the dataset so a refresh job or a test can
 * pass a different list.
 */
export function groupByModality(
  models: BenchmarkModel[] = BENCHMARK_MODELS,
): ModalityGroup[] {
  const tierRank: Record<Tier, number> = {
    "standardize-now": 0,
    "efficiency-pick": 1,
    watch: 2,
  };
  return MODALITY_ORDER.map((modality) => {
    const group = models
      .filter((m) => m.modality === modality)
      .sort((a, b) => {
        const tierDelta = tierRank[a.tier] - tierRank[b.tier];
        if (tierDelta !== 0) return tierDelta;
        return bestValueScore(b) - bestValueScore(a);
      });
    return { modality, label: MODALITY_LABELS[modality], models: group };
  }).filter((g) => g.models.length > 0);
}
