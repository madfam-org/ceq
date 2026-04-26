"""
Smart Provider Router

Routes CEQ jobs to the optimal GPU provider based on workload type:
- Image generation (Flux, SDXL) → fal.ai (serverless, fast, per-request)
- Video generation (Hunyuan) → Vast.ai (instance-based, high VRAM)
- 3D generation (TriposR) → fal.ai or Vast.ai (either works)
- Custom ComfyUI workflows → Vast.ai (full Docker environment)

Set FAL_API_KEY to enable fal.ai routing. Without it, all jobs go to the
primary provider (Vast.ai by default).
"""

import os
from typing import Any

from ceq_worker.providers.base import GPUProvider
from ceq_worker.providers.fal import FalAIProvider

# Templates/categories that should route to fal.ai (fast, cheap, serverless)
FAL_ELIGIBLE_CATEGORIES = {"social", "utility"}

# VRAM thresholds — jobs requiring >24GB VRAM should use instance providers
FAL_MAX_VRAM_GB = 24.0


class ProviderRouter:
    """
    Routes jobs to the best provider based on workload characteristics.

    When fal.ai is configured (FAL_API_KEY set), image-generation jobs
    are routed there for faster execution and lower cost. Everything else
    goes to the primary instance-based provider (Vast.ai/Furnace).
    """

    def __init__(
        self,
        primary_provider: GPUProvider,
        fal_provider: FalAIProvider | None = None,
    ) -> None:
        self.primary = primary_provider
        self.fal = fal_provider
        self._fal_initialized = False

    @classmethod
    async def create(cls, primary_provider: GPUProvider) -> "ProviderRouter":
        """Factory that auto-detects fal.ai availability."""
        fal_key = os.getenv("FAL_API_KEY", "")
        fal_provider = None

        if fal_key:
            fal_provider = FalAIProvider()
            try:
                await fal_provider.initialize()
                print("🔀 Provider router: fal.ai enabled for image jobs")
            except Exception as e:
                print(f"⚠️ fal.ai init failed ({e}), all jobs will use primary provider")
                fal_provider = None

        return cls(primary_provider, fal_provider)

    def should_use_fal(self, job: dict[str, Any]) -> bool:
        """
        Determine if a job should be routed to fal.ai.

        Returns True if:
        1. fal.ai is configured and initialized
        2. The job's model requirements match a fal.ai endpoint
        3. The VRAM requirement is within fal.ai's range
        4. The job category is eligible for serverless execution
        """
        if not self.fal:
            return False

        input_data = job.get("input", {})
        template = input_data.get("template", {})

        # Check VRAM requirement
        vram_req = template.get("vram_requirement_gb", 16)
        if vram_req > FAL_MAX_VRAM_GB:
            return False

        # Check category
        category = template.get("category", "")
        if category and category not in FAL_ELIGIBLE_CATEGORIES:
            # Video and 3D categories go to instance providers
            return False

        # Check if model requirements match a fal.ai endpoint
        model_reqs = template.get("model_requirements", [])
        return bool(model_reqs and self.fal.resolve_endpoint(model_reqs))

    async def execute_on_fal(self, job: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a job on fal.ai's serverless API.

        Translates the CEQ job format to fal.ai parameters and returns
        results in CEQ's standard output format.
        """
        assert self.fal, "fal.ai provider not available"

        input_data = job.get("input", {})
        params = input_data.get("params", {})
        template = input_data.get("template", {})
        job_id = job.get("id", "unknown")

        # Resolve the fal.ai endpoint
        model_reqs = template.get("model_requirements", [])
        endpoint = self.fal.resolve_endpoint(model_reqs)

        if not endpoint:
            raise ValueError(f"No fal.ai endpoint for models: {model_reqs}")

        # Map CEQ params to fal.ai format
        fal_params = self._map_params(endpoint, params)

        print(f"🚀 Routing job {job_id} to fal.ai ({endpoint})")

        # Execute synchronously (fal.ai is fast enough for blocking calls)
        result = await self.fal.run_sync(endpoint, fal_params)

        # Map fal.ai result back to CEQ format
        return self._map_result(result, job_id)

    def _map_params(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """Map CEQ parameters to fal.ai API format."""
        fal_params: dict[str, Any] = {}

        if "flux" in endpoint:
            fal_params["prompt"] = params.get("prompt", "")
            fal_params["image_size"] = {
                "width": params.get("width", 1024),
                "height": params.get("height", 1024),
            }
            if params.get("seed", -1) >= 0:
                fal_params["seed"] = params["seed"]
            fal_params["num_inference_steps"] = params.get("steps", 4)

        elif "sdxl" in endpoint:
            fal_params["prompt"] = params.get("prompt", "")
            fal_params["negative_prompt"] = params.get("negative_prompt", "")
            fal_params["image_size"] = {
                "width": params.get("width", 1024),
                "height": params.get("height", 1024),
            }
            if params.get("seed", -1) >= 0:
                fal_params["seed"] = params["seed"]
            fal_params["num_inference_steps"] = params.get("steps", 30)
            fal_params["guidance_scale"] = params.get("cfg_scale", 7.5)

        elif "triposr" in endpoint:
            fal_params["image_url"] = params.get("image_url", "")

        else:
            # Generic passthrough for unknown endpoints
            fal_params = params

        return fal_params

    def _map_result(self, fal_result: dict[str, Any], job_id: str) -> dict[str, Any]:
        """Map fal.ai result to CEQ output format."""
        output_urls = []

        # fal.ai returns images in various formats depending on endpoint
        if "images" in fal_result:
            for img in fal_result["images"]:
                if isinstance(img, dict):
                    output_urls.append(img.get("url", ""))
                elif isinstance(img, str):
                    output_urls.append(img)

        elif "image" in fal_result:
            img = fal_result["image"]
            if isinstance(img, dict):
                output_urls.append(img.get("url", ""))
            elif isinstance(img, str):
                output_urls.append(img)

        elif "model_mesh" in fal_result:
            # TriposR returns a 3D mesh
            mesh = fal_result["model_mesh"]
            if isinstance(mesh, dict):
                output_urls.append(mesh.get("url", ""))

        return {
            "success": True,
            "output_urls": output_urls,
            "metadata": {
                "provider": "fal",
                "fal_request_id": fal_result.get("request_id"),
                "timings": fal_result.get("timings", {}),
            },
            "execution_time": sum(fal_result.get("timings", {}).values()) if fal_result.get("timings") else 0,
        }
