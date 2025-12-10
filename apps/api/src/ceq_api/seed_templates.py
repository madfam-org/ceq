"""
Seed templates derived from ZHO-ZHO-ZHO/ComfyUI-Workflows-ZHO collection.
These templates provide production-ready workflows for CEQ users.
"""

from typing import Any

# Template definitions based on ZHO workflows collection
SEED_TEMPLATES: list[dict[str, Any]] = [
    # ═══════════════════════════════════════════════════════════════════
    # SOCIAL / IMAGE GENERATION
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "FLUX.1 DEV",
        "description": "High-quality image generation with FLUX.1 DEV model. Excellent for detailed, photorealistic outputs.",
        "category": "social",
        "tags": ["flux", "image-gen", "photorealistic", "high-quality"],
        "model_requirements": ["flux1-dev.safetensors", "clip_l.safetensors", "t5xxl_fp16.safetensors"],
        "vram_requirement_gb": 24,
        "input_schema": {
            "prompt": {"type": "string", "description": "Text prompt for image generation", "required": True},
            "negative_prompt": {"type": "string", "description": "Negative prompt", "default": ""},
            "width": {"type": "integer", "default": 1024, "min": 512, "max": 2048},
            "height": {"type": "integer", "default": 1024, "min": 512, "max": 2048},
            "steps": {"type": "integer", "default": 20, "min": 1, "max": 50},
            "cfg": {"type": "number", "default": 3.5, "min": 1.0, "max": 10.0},
            "seed": {"type": "integer", "default": -1, "description": "-1 for random"},
        },
        "workflow_json": {
            "nodes": [
                {"id": "1", "type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-dev.safetensors"}},
                {"id": "2", "type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["1", 1]}},
                {"id": "3", "type": "CLIPTextEncode", "inputs": {"text": "{{negative_prompt}}", "clip": ["1", 1]}},
                {"id": "4", "type": "EmptyLatentImage", "inputs": {"width": "{{width}}", "height": "{{height}}", "batch_size": 1}},
                {"id": "5", "type": "KSampler", "inputs": {
                    "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
                    "seed": "{{seed}}", "steps": "{{steps}}", "cfg": "{{cfg}}", "sampler_name": "euler", "scheduler": "normal"
                }},
                {"id": "6", "type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
                {"id": "7", "type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "flux_dev"}}
            ]
        },
    },
    {
        "name": "FLUX.1 SCHNELL",
        "description": "Fast image generation with FLUX.1 SCHNELL. Optimized for speed with 4-step generation.",
        "category": "social",
        "tags": ["flux", "fast", "image-gen", "schnell"],
        "model_requirements": ["flux1-schnell.safetensors"],
        "vram_requirement_gb": 16,
        "input_schema": {
            "prompt": {"type": "string", "required": True},
            "width": {"type": "integer", "default": 1024},
            "height": {"type": "integer", "default": 1024},
            "seed": {"type": "integer", "default": -1},
        },
        "workflow_json": {
            "nodes": [
                {"id": "1", "type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-schnell.safetensors"}},
                {"id": "2", "type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["1", 1]}},
                {"id": "3", "type": "EmptyLatentImage", "inputs": {"width": "{{width}}", "height": "{{height}}", "batch_size": 1}},
                {"id": "4", "type": "KSampler", "inputs": {
                    "model": ["1", 0], "positive": ["2", 0], "negative": None, "latent_image": ["3", 0],
                    "seed": "{{seed}}", "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple"
                }},
                {"id": "5", "type": "VAEDecode", "inputs": {"samples": ["4", 0], "vae": ["1", 2]}},
                {"id": "6", "type": "SaveImage", "inputs": {"images": ["5", 0], "filename_prefix": "flux_schnell"}}
            ]
        },
    },
    {
        "name": "SD3 Medium",
        "description": "Stable Diffusion 3 Medium - next-gen image generation with improved text rendering.",
        "category": "social",
        "tags": ["sd3", "stable-diffusion", "text-rendering", "image-gen"],
        "model_requirements": ["sd3_medium.safetensors"],
        "vram_requirement_gb": 16,
        "input_schema": {
            "prompt": {"type": "string", "required": True},
            "negative_prompt": {"type": "string", "default": ""},
            "width": {"type": "integer", "default": 1024},
            "height": {"type": "integer", "default": 1024},
            "steps": {"type": "integer", "default": 28},
            "cfg": {"type": "number", "default": 4.5},
            "seed": {"type": "integer", "default": -1},
        },
        "workflow_json": {
            "nodes": [
                {"id": "1", "type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd3_medium.safetensors"}},
                {"id": "2", "type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["1", 1]}},
                {"id": "3", "type": "CLIPTextEncode", "inputs": {"text": "{{negative_prompt}}", "clip": ["1", 1]}},
                {"id": "4", "type": "EmptyLatentImage", "inputs": {"width": "{{width}}", "height": "{{height}}", "batch_size": 1}},
                {"id": "5", "type": "KSampler", "inputs": {
                    "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
                    "seed": "{{seed}}", "steps": "{{steps}}", "cfg": "{{cfg}}", "sampler_name": "dpmpp_2m", "scheduler": "sgm_uniform"
                }},
                {"id": "6", "type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
                {"id": "7", "type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "sd3_medium"}}
            ]
        },
    },
    {
        "name": "InstantID Portrait",
        "description": "Identity-preserving portrait generation. Upload a face photo to generate new images with the same identity.",
        "category": "social",
        "tags": ["instantid", "portrait", "face", "identity", "ip-adapter"],
        "model_requirements": ["instantid-ip-adapter.bin", "antelopev2"],
        "vram_requirement_gb": 12,
        "input_schema": {
            "face_image": {"type": "image", "required": True, "description": "Reference face image"},
            "prompt": {"type": "string", "required": True},
            "negative_prompt": {"type": "string", "default": "blurry, low quality"},
            "ip_adapter_weight": {"type": "number", "default": 0.8, "min": 0.0, "max": 1.5},
            "seed": {"type": "integer", "default": -1},
        },
        "workflow_json": {
            "nodes": [
                {"id": "1", "type": "LoadImage", "inputs": {"image": "{{face_image}}"}},
                {"id": "2", "type": "InstantIDFaceAnalysis", "inputs": {"image": ["1", 0]}},
                {"id": "3", "type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sdxl_base.safetensors"}},
                {"id": "4", "type": "InstantIDModelLoader", "inputs": {}},
                {"id": "5", "type": "ApplyInstantID", "inputs": {
                    "model": ["3", 0], "instantid": ["4", 0], "face_embeds": ["2", 0],
                    "weight": "{{ip_adapter_weight}}"
                }},
                {"id": "6", "type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["3", 1]}},
                {"id": "7", "type": "CLIPTextEncode", "inputs": {"text": "{{negative_prompt}}", "clip": ["3", 1]}},
                {"id": "8", "type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
                {"id": "9", "type": "KSampler", "inputs": {
                    "model": ["5", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["8", 0],
                    "seed": "{{seed}}", "steps": 25, "cfg": 5.0
                }},
                {"id": "10", "type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 2]}},
                {"id": "11", "type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": "instantid"}}
            ]
        },
    },

    # ═══════════════════════════════════════════════════════════════════
    # VIDEO GENERATION
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "Hunyuan Video 1.0",
        "description": "Text-to-video generation using Hunyuan Video model. Create short video clips from text descriptions.",
        "category": "video",
        "tags": ["hunyuan", "text-to-video", "video-gen", "animation"],
        "model_requirements": ["hunyuan_video_720_cfgdistill_fp8.safetensors"],
        "vram_requirement_gb": 24,
        "input_schema": {
            "prompt": {"type": "string", "required": True, "description": "Video description"},
            "negative_prompt": {"type": "string", "default": "blurry, low quality, distorted"},
            "frames": {"type": "integer", "default": 49, "min": 25, "max": 129},
            "width": {"type": "integer", "default": 848},
            "height": {"type": "integer", "default": 480},
            "steps": {"type": "integer", "default": 30},
            "cfg": {"type": "number", "default": 6.0},
            "seed": {"type": "integer", "default": -1},
        },
        "workflow_json": {
            "nodes": [
                {"id": "1", "type": "HunyuanVideoModelLoader", "inputs": {"model": "hunyuan_video_720_cfgdistill_fp8.safetensors"}},
                {"id": "2", "type": "HunyuanVideoCLIPLoader", "inputs": {}},
                {"id": "3", "type": "HunyuanVideoTextEncode", "inputs": {"prompt": "{{prompt}}", "clip": ["2", 0]}},
                {"id": "4", "type": "HunyuanVideoTextEncode", "inputs": {"prompt": "{{negative_prompt}}", "clip": ["2", 0]}},
                {"id": "5", "type": "HunyuanVideoEmptyLatent", "inputs": {"width": "{{width}}", "height": "{{height}}", "frames": "{{frames}}"}},
                {"id": "6", "type": "HunyuanVideoSampler", "inputs": {
                    "model": ["1", 0], "positive": ["3", 0], "negative": ["4", 0], "latent": ["5", 0],
                    "steps": "{{steps}}", "cfg": "{{cfg}}", "seed": "{{seed}}"
                }},
                {"id": "7", "type": "HunyuanVideoVAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 1]}},
                {"id": "8", "type": "VHS_VideoCombine", "inputs": {"images": ["7", 0], "frame_rate": 24, "format": "video/mp4"}}
            ]
        },
    },
    {
        "name": "I2VGen-XL Image to Video",
        "description": "Convert a static image into an animated video clip. Great for bringing photos to life.",
        "category": "video",
        "tags": ["i2vgen", "image-to-video", "animation", "video-gen"],
        "model_requirements": ["i2vgen-xl.safetensors"],
        "vram_requirement_gb": 16,
        "input_schema": {
            "image": {"type": "image", "required": True, "description": "Input image to animate"},
            "prompt": {"type": "string", "required": True, "description": "Motion/animation description"},
            "frames": {"type": "integer", "default": 16, "min": 8, "max": 32},
            "fps": {"type": "integer", "default": 8},
            "seed": {"type": "integer", "default": -1},
        },
        "workflow_json": {
            "nodes": [
                {"id": "1", "type": "LoadImage", "inputs": {"image": "{{image}}"}},
                {"id": "2", "type": "I2VGenXLModelLoader", "inputs": {}},
                {"id": "3", "type": "I2VGenXLSampler", "inputs": {
                    "model": ["2", 0], "image": ["1", 0], "prompt": "{{prompt}}",
                    "frames": "{{frames}}", "seed": "{{seed}}"
                }},
                {"id": "4", "type": "VHS_VideoCombine", "inputs": {"images": ["3", 0], "frame_rate": "{{fps}}", "format": "video/mp4"}}
            ]
        },
    },
    {
        "name": "LivePortrait Animals",
        "description": "Animate animal photos with facial expressions and movements. Perfect for pet photos.",
        "category": "video",
        "tags": ["liveportrait", "animals", "animation", "face-animation"],
        "model_requirements": ["liveportrait_animals.onnx"],
        "vram_requirement_gb": 8,
        "input_schema": {
            "source_image": {"type": "image", "required": True, "description": "Animal face photo"},
            "driving_video": {"type": "video", "required": True, "description": "Motion reference video"},
            "relative_motion": {"type": "boolean", "default": True},
        },
        "workflow_json": {
            "nodes": [
                {"id": "1", "type": "LoadImage", "inputs": {"image": "{{source_image}}"}},
                {"id": "2", "type": "VHS_LoadVideo", "inputs": {"video": "{{driving_video}}"}},
                {"id": "3", "type": "LivePortraitAnimalsLoader", "inputs": {}},
                {"id": "4", "type": "LivePortraitProcess", "inputs": {
                    "model": ["3", 0], "source": ["1", 0], "driving": ["2", 0],
                    "relative_motion": "{{relative_motion}}"
                }},
                {"id": "5", "type": "VHS_VideoCombine", "inputs": {"images": ["4", 0], "frame_rate": 30, "format": "video/mp4"}}
            ]
        },
    },

    # ═══════════════════════════════════════════════════════════════════
    # 3D GENERATION
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "CRM 3D Model Generator",
        "description": "Generate 3D models from a single image. Outputs GLB format for use in games, AR/VR, and 3D printing.",
        "category": "3d",
        "tags": ["3d", "crm", "mesh", "glb", "3d-gen"],
        "model_requirements": ["crm_model.safetensors"],
        "vram_requirement_gb": 16,
        "input_schema": {
            "image": {"type": "image", "required": True, "description": "Input image for 3D reconstruction"},
            "remove_background": {"type": "boolean", "default": True},
            "mesh_resolution": {"type": "integer", "default": 256, "min": 128, "max": 512},
        },
        "workflow_json": {
            "nodes": [
                {"id": "1", "type": "LoadImage", "inputs": {"image": "{{image}}"}},
                {"id": "2", "type": "RMBG", "inputs": {"image": ["1", 0]}, "enabled": "{{remove_background}}"},
                {"id": "3", "type": "CRMModelLoader", "inputs": {}},
                {"id": "4", "type": "CRMGenerate3D", "inputs": {
                    "model": ["3", 0], "image": ["2", 0], "resolution": "{{mesh_resolution}}"
                }},
                {"id": "5", "type": "Save3DModel", "inputs": {"mesh": ["4", 0], "format": "glb", "filename_prefix": "crm_3d"}}
            ]
        },
    },
    {
        "name": "Sketch to 3D",
        "description": "Convert hand-drawn sketches into 3D models. Uses Playground v2.5 for sketch enhancement before 3D conversion.",
        "category": "3d",
        "tags": ["sketch", "3d", "drawing", "concept-art", "triposr"],
        "model_requirements": ["playground-v2.5.safetensors", "triposr_model.safetensors"],
        "vram_requirement_gb": 20,
        "input_schema": {
            "sketch": {"type": "image", "required": True, "description": "Hand-drawn sketch"},
            "prompt": {"type": "string", "default": "", "description": "Optional: describe the object"},
            "enhance_sketch": {"type": "boolean", "default": True},
        },
        "workflow_json": {
            "nodes": [
                {"id": "1", "type": "LoadImage", "inputs": {"image": "{{sketch}}"}},
                {"id": "2", "type": "CannyEdgePreprocessor", "inputs": {"image": ["1", 0]}},
                {"id": "3", "type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "playground-v2.5.safetensors"}},
                {"id": "4", "type": "ControlNetLoader", "inputs": {"control_net_name": "control_canny_sdxl.safetensors"}},
                {"id": "5", "type": "ControlNetApply", "inputs": {"conditioning": None, "control_net": ["4", 0], "image": ["2", 0]}},
                {"id": "6", "type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}, 3d model, isometric view, white background", "clip": ["3", 1]}},
                {"id": "7", "type": "KSampler", "inputs": {"model": ["3", 0], "positive": ["5", 0]}},
                {"id": "8", "type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 2]}},
                {"id": "9", "type": "TripoSRModelLoader", "inputs": {}},
                {"id": "10", "type": "TripoSRGenerate", "inputs": {"model": ["9", 0], "image": ["8", 0]}},
                {"id": "11", "type": "Save3DModel", "inputs": {"mesh": ["10", 0], "format": "glb", "filename_prefix": "sketch_3d"}}
            ]
        },
    },
    {
        "name": "LayerDiffusion + TripoSR",
        "description": "Generate transparent PNG images with LayerDiffusion, then convert to 3D. Perfect for game assets.",
        "category": "3d",
        "tags": ["layerdiffusion", "triposr", "transparent", "game-assets", "3d"],
        "model_requirements": ["sdxl_base.safetensors", "layer_diffusion_sdxl.safetensors", "triposr_model.safetensors"],
        "vram_requirement_gb": 20,
        "input_schema": {
            "prompt": {"type": "string", "required": True, "description": "Object description"},
            "negative_prompt": {"type": "string", "default": "background, scene"},
            "seed": {"type": "integer", "default": -1},
        },
        "workflow_json": {
            "nodes": [
                {"id": "1", "type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sdxl_base.safetensors"}},
                {"id": "2", "type": "LayerDiffusionLoader", "inputs": {}},
                {"id": "3", "type": "LayerDiffusionApply", "inputs": {"model": ["1", 0], "layer_diffusion": ["2", 0]}},
                {"id": "4", "type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["1", 1]}},
                {"id": "5", "type": "CLIPTextEncode", "inputs": {"text": "{{negative_prompt}}", "clip": ["1", 1]}},
                {"id": "6", "type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
                {"id": "7", "type": "KSampler", "inputs": {
                    "model": ["3", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0],
                    "seed": "{{seed}}", "steps": 25, "cfg": 7.0
                }},
                {"id": "8", "type": "LayerDiffusionDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
                {"id": "9", "type": "TripoSRModelLoader", "inputs": {}},
                {"id": "10", "type": "TripoSRGenerate", "inputs": {"model": ["9", 0], "image": ["8", 0]}},
                {"id": "11", "type": "Save3DModel", "inputs": {"mesh": ["10", 0], "format": "glb", "filename_prefix": "layer_3d"}}
            ]
        },
    },

    # ═══════════════════════════════════════════════════════════════════
    # UTILITY
    # ═══════════════════════════════════════════════════════════════════
    {
        "name": "APISR 4x Upscale",
        "description": "AI-powered image upscaling with APISR. Enhance resolution by 4x while preserving details.",
        "category": "utility",
        "tags": ["upscale", "apisr", "enhance", "super-resolution"],
        "model_requirements": ["apisr_4x.safetensors"],
        "vram_requirement_gb": 8,
        "input_schema": {
            "image": {"type": "image", "required": True},
            "scale": {"type": "integer", "default": 4, "enum": [2, 4]},
        },
        "workflow_json": {
            "nodes": [
                {"id": "1", "type": "LoadImage", "inputs": {"image": "{{image}}"}},
                {"id": "2", "type": "APISRModelLoader", "inputs": {"model_name": "apisr_{{scale}}x.safetensors"}},
                {"id": "3", "type": "APISRUpscale", "inputs": {"model": ["2", 0], "image": ["1", 0]}},
                {"id": "4", "type": "SaveImage", "inputs": {"images": ["3", 0], "filename_prefix": "upscaled"}}
            ]
        },
    },
    {
        "name": "YoloWorld + SAM Segmentation",
        "description": "Detect and segment objects using YoloWorld detection with SAM refinement. Extract objects from images.",
        "category": "utility",
        "tags": ["yolo", "sam", "segmentation", "detection", "object-extraction"],
        "model_requirements": ["yolov8x-worldv2.pt", "sam_vit_h.pth"],
        "vram_requirement_gb": 12,
        "input_schema": {
            "image": {"type": "image", "required": True},
            "categories": {"type": "string", "required": True, "description": "Comma-separated object categories to detect"},
            "confidence_threshold": {"type": "number", "default": 0.3, "min": 0.1, "max": 0.9},
        },
        "workflow_json": {
            "nodes": [
                {"id": "1", "type": "LoadImage", "inputs": {"image": "{{image}}"}},
                {"id": "2", "type": "YoloWorldModelLoader", "inputs": {"model_name": "yolov8x-worldv2.pt"}},
                {"id": "3", "type": "YoloWorldDetect", "inputs": {
                    "model": ["2", 0], "image": ["1", 0], "categories": "{{categories}}",
                    "confidence": "{{confidence_threshold}}"
                }},
                {"id": "4", "type": "SAMModelLoader", "inputs": {"model_name": "sam_vit_h.pth"}},
                {"id": "5", "type": "SAMSegment", "inputs": {"model": ["4", 0], "image": ["1", 0], "boxes": ["3", 0]}},
                {"id": "6", "type": "SaveImage", "inputs": {"images": ["5", 0], "filename_prefix": "segmented"}}
            ]
        },
    },
    {
        "name": "Differential Diffusion Inpaint",
        "description": "Advanced inpainting with variable strength control. Paint over areas to regenerate with fine-grained control.",
        "category": "utility",
        "tags": ["inpaint", "differential-diffusion", "editing", "mask"],
        "model_requirements": ["sdxl_base.safetensors"],
        "vram_requirement_gb": 12,
        "input_schema": {
            "image": {"type": "image", "required": True},
            "mask": {"type": "image", "required": True, "description": "Grayscale mask - white=full change, black=no change"},
            "prompt": {"type": "string", "required": True},
            "negative_prompt": {"type": "string", "default": ""},
            "denoise_strength": {"type": "number", "default": 0.85, "min": 0.0, "max": 1.0},
            "seed": {"type": "integer", "default": -1},
        },
        "workflow_json": {
            "nodes": [
                {"id": "1", "type": "LoadImage", "inputs": {"image": "{{image}}"}},
                {"id": "2", "type": "LoadImage", "inputs": {"image": "{{mask}}"}},
                {"id": "3", "type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sdxl_base.safetensors"}},
                {"id": "4", "type": "DifferentialDiffusion", "inputs": {"model": ["3", 0]}},
                {"id": "5", "type": "VAEEncode", "inputs": {"pixels": ["1", 0], "vae": ["3", 2]}},
                {"id": "6", "type": "SetLatentNoiseMask", "inputs": {"samples": ["5", 0], "mask": ["2", 0]}},
                {"id": "7", "type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["3", 1]}},
                {"id": "8", "type": "CLIPTextEncode", "inputs": {"text": "{{negative_prompt}}", "clip": ["3", 1]}},
                {"id": "9", "type": "KSampler", "inputs": {
                    "model": ["4", 0], "positive": ["7", 0], "negative": ["8", 0], "latent_image": ["6", 0],
                    "seed": "{{seed}}", "steps": 25, "cfg": 7.0, "denoise": "{{denoise_strength}}"
                }},
                {"id": "10", "type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 2]}},
                {"id": "11", "type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": "inpainted"}}
            ]
        },
    },
]


def get_templates_by_category(category: str) -> list[dict[str, Any]]:
    """Filter templates by category."""
    return [t for t in SEED_TEMPLATES if t["category"] == category]


def get_template_by_name(name: str) -> dict[str, Any] | None:
    """Find a template by name."""
    for t in SEED_TEMPLATES:
        if t["name"].lower() == name.lower():
            return t
    return None


def get_all_categories() -> list[str]:
    """Get unique categories."""
    return list(set(t["category"] for t in SEED_TEMPLATES))


def get_all_tags() -> list[str]:
    """Get all unique tags."""
    tags = set()
    for t in SEED_TEMPLATES:
        tags.update(t.get("tags", []))
    return sorted(tags)
