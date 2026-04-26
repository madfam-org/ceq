"""
fal.ai API Provider Implementation

Implements the GPUProvider interface for fal.ai serverless API.
https://fal.ai/docs

Unlike Vast.ai (which manages Docker instances), fal.ai is an API-based
provider — it runs workflows serverlessly with sub-second cold starts
and per-request billing. No instance lifecycle management needed.

Best suited for:
- Fast image generation (Flux Schnell <1s, SDXL ~5s)
- Per-image billing ($0.025/image) — cheaper than instance-hours for burst workloads
- Jobs that match fal.ai's supported model catalog

Not suited for:
- Custom ComfyUI workflows with exotic nodes
- Video generation requiring 80GB+ VRAM (use Vast.ai)
- Jobs needing persistent model state between calls
"""

import asyncio
import os
import time
from typing import Any
from uuid import uuid4

import httpx

from ceq_worker.providers.base import (
    GPUProvider,
    GPUTier,
    InstanceInfo,
    InstanceSpec,
    InstanceStatus,
    ProviderConfig,
)

# fal.ai model endpoint mapping
# Maps CEQ template names / model requirements to fal.ai endpoint IDs
FAL_MODEL_ENDPOINTS: dict[str, str] = {
    # Flux models
    "flux1-schnell": "fal-ai/flux/schnell",
    "flux1-schnell.safetensors": "fal-ai/flux/schnell",
    "flux1-dev": "fal-ai/flux/dev",
    "flux1-dev.safetensors": "fal-ai/flux/dev",
    # SDXL
    "sdxl": "fal-ai/fast-sdxl",
    "sd_xl_base_1.0.safetensors": "fal-ai/fast-sdxl",
    # TriposR (3D)
    "triposr": "fal-ai/triposr",
    # ComfyUI (generic — runs any workflow)
    "comfyui": "fal-ai/comfy/run",
}

# Default fal.ai pricing (approximate $/image for standard models)
FAL_PRICING: dict[str, float] = {
    "fal-ai/flux/schnell": 0.015,
    "fal-ai/flux/dev": 0.025,
    "fal-ai/fast-sdxl": 0.020,
    "fal-ai/triposr": 0.050,
    "fal-ai/comfy/run": 0.030,  # varies by workflow complexity
}


class FalAIProvider(GPUProvider):
    """
    fal.ai serverless API provider.

    This provider delegates generation to fal.ai's hosted endpoints
    instead of managing GPU instances. It's designed for fast, stateless
    image generation jobs where sub-second cold starts and per-request
    billing are more cost-effective than spinning up instances.

    Instance lifecycle methods are no-ops since fal.ai is serverless.
    The core value is in `submit_job()` and `get_job_result()`.
    """

    API_BASE = "https://queue.fal.run"
    REST_BASE = "https://rest.fal.run"

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)
        self._client: httpx.AsyncClient | None = None
        self._jobs: dict[str, dict[str, Any]] = {}  # track submitted jobs

    def _load_config(self) -> ProviderConfig:
        """Load config from environment variables."""
        return ProviderConfig(
            api_key=os.getenv("FAL_API_KEY", ""),
            api_url=self.API_BASE,
            max_price_per_hour=float(os.getenv("FAL_MAX_HOURLY_SPEND", "5.0")),
            max_instances=1,  # serverless — no instance concept
            scale_to_zero=True,
            idle_timeout_seconds=0,
        )

    async def initialize(self) -> None:
        """Initialize fal.ai client and validate API key."""
        if self._initialized:
            return

        if not self.config.api_key:
            raise RuntimeError("FAL_API_KEY environment variable is required")

        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Key {self.config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

        # Validate API key with a lightweight request
        try:
            resp = await self._client.get("https://rest.fal.run/fal-ai/flux/schnell")
            # 401 = bad key, 405/422 = key works (method not allowed for GET)
            if resp.status_code == 401:
                raise RuntimeError("Invalid FAL_API_KEY")
        except httpx.ConnectError as e:
            raise RuntimeError(f"Cannot connect to fal.ai: {e}") from e

        self._initialized = True
        print("⚡ fal.ai provider initialized (serverless API mode)")

    # =================================================================
    # Core API Methods (fal.ai specific)
    # =================================================================

    async def submit_job(
        self,
        model: str,
        params: dict[str, Any],
        webhook_url: str | None = None,
    ) -> dict[str, Any]:
        """
        Submit a generation job to fal.ai.

        Args:
            model: Model key (from FAL_MODEL_ENDPOINTS) or direct fal endpoint ID
            params: Model-specific parameters (prompt, width, height, etc.)
            webhook_url: Optional webhook for completion notification

        Returns:
            Dict with request_id and status_url for polling
        """
        assert self._client, "Provider not initialized"

        endpoint = FAL_MODEL_ENDPOINTS.get(model, model)
        url = f"{self.API_BASE}/{endpoint}"

        payload: dict[str, Any] = {**params}
        if webhook_url:
            payload["webhook_url"] = webhook_url

        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()

        result = resp.json()
        job_id = result.get("request_id", str(uuid4()))

        self._jobs[job_id] = {
            "endpoint": endpoint,
            "status": "queued",
            "submitted_at": time.time(),
        }

        return {
            "request_id": job_id,
            "status_url": result.get("status_url", f"{self.API_BASE}/{endpoint}/requests/{job_id}/status"),
            "response_url": result.get("response_url", f"{self.API_BASE}/{endpoint}/requests/{job_id}"),
        }

    async def get_job_result(
        self,
        endpoint: str,
        request_id: str,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """
        Poll for job completion and return the result.

        Args:
            endpoint: fal.ai endpoint ID
            request_id: Job request ID from submit_job
            timeout: Max seconds to wait

        Returns:
            Job result dict with images/outputs
        """
        assert self._client, "Provider not initialized"

        result_url = f"{self.API_BASE}/{endpoint}/requests/{request_id}"
        status_url = f"{result_url}/status"

        start = time.time()
        while time.time() - start < timeout:
            resp = await self._client.get(status_url)
            resp.raise_for_status()
            status = resp.json()

            if status.get("status") == "COMPLETED":
                # Fetch full result
                result_resp = await self._client.get(result_url)
                result_resp.raise_for_status()
                return result_resp.json()

            if status.get("status") in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"fal.ai job failed: {status.get('error', 'unknown')}")

            await asyncio.sleep(0.5)

        raise TimeoutError(f"fal.ai job {request_id} timed out after {timeout}s")

    async def run_sync(
        self,
        model: str,
        params: dict[str, Any],
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """
        Submit a job and wait for the result synchronously.

        This is the simplest way to use fal.ai — submit and wait.

        Args:
            model: Model key or fal endpoint ID
            params: Model parameters

        Returns:
            Generation result with image URLs
        """
        assert self._client, "Provider not initialized"

        endpoint = FAL_MODEL_ENDPOINTS.get(model, model)
        url = f"{self.REST_BASE}/{endpoint}"

        resp = await self._client.post(url, json=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def resolve_endpoint(self, model_requirements: list[str]) -> str | None:
        """
        Resolve CEQ model requirements to a fal.ai endpoint.

        Args:
            model_requirements: List of model file names from the template

        Returns:
            fal.ai endpoint ID if a match is found, None otherwise
        """
        for req in model_requirements:
            req_lower = req.lower().replace(".safetensors", "").replace("-", "")
            for key, endpoint in FAL_MODEL_ENDPOINTS.items():
                if req_lower in key.lower().replace("-", "").replace(".safetensors", ""):
                    return endpoint
        return None

    def estimate_cost(self, model: str, count: int = 1, **_) -> float:
        """Estimate cost for a batch of generations."""
        endpoint = FAL_MODEL_ENDPOINTS.get(model, model)
        per_image = FAL_PRICING.get(endpoint, 0.03)
        return per_image * count

    # =================================================================
    # GPUProvider Interface (instance management — mostly no-ops)
    # =================================================================

    async def create_instance(self, spec: InstanceSpec) -> InstanceInfo:
        """No-op: fal.ai is serverless. Returns a virtual instance."""
        return InstanceInfo(
            id=f"fal-serverless-{uuid4().hex[:8]}",
            provider="fal",
            status=InstanceStatus.RUNNING,
            gpu_type="serverless",
            gpu_count=0,
            price_per_hour=0.0,
            region="fal-cloud",
        )

    async def start_instance(self, instance_id: str) -> InstanceInfo:
        return await self.get_instance(instance_id)

    async def stop_instance(self, instance_id: str) -> InstanceInfo:
        return InstanceInfo(
            id=instance_id, provider="fal",
            status=InstanceStatus.STOPPED, gpu_type="serverless", gpu_count=0,
        )

    async def destroy_instance(self, instance_id: str) -> None:
        self._jobs.pop(instance_id, None)

    async def get_instance(self, instance_id: str) -> InstanceInfo:
        return InstanceInfo(
            id=instance_id, provider="fal",
            status=InstanceStatus.RUNNING, gpu_type="serverless", gpu_count=0,
        )

    async def list_instances(self, labels: dict[str, str] | None = None) -> list[InstanceInfo]:
        return []  # serverless — no persistent instances

    async def list_available_gpus(
        self, min_vram_gb: float = 0,
        max_price_per_hour: float | None = None,
        region: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return fal.ai's virtual GPU offering."""
        return [
            {"gpu_type": "fal-serverless", "vram_gb": 80, "price_per_hour": 0.0,
             "available_count": 999, "region": "fal-cloud",
             "note": "Serverless — billed per request, not per hour"},
        ]

    async def find_cheapest_gpu(
        self, min_vram_gb: float = 16, gpu_tier: GPUTier | None = None,
    ) -> dict[str, Any] | None:
        return {"gpu_type": "fal-serverless", "vram_gb": 80, "price_per_hour": 0.0,
                "provider": "fal", "note": "Per-request billing"}

    async def is_instance_healthy(self, instance_id: str) -> bool:
        return True  # serverless is always "healthy"

    async def get_instance_logs(self, instance_id: str, tail: int = 100) -> str:
        return "[fal.ai serverless — no instance logs. Check fal.ai dashboard for job logs.]"

    async def get_usage_stats(self) -> dict[str, Any]:
        return {
            "provider": "fal",
            "mode": "serverless",
            "active_instances": 0,
            "total_jobs_submitted": len(self._jobs),
            "note": "Billing is per-request. Check fal.ai dashboard for spend.",
        }

    async def ssh_command(self, instance_id: str, command: str, timeout: int = 60) -> tuple[str, str, int]:
        return ("", "SSH not supported for serverless provider", 1)

    async def upload_file(self, instance_id: str, local_path: str, remote_path: str) -> None:
        raise NotImplementedError("File upload not supported for serverless provider. Use fal.ai storage API.")

    async def download_file(self, instance_id: str, remote_path: str, local_path: str) -> None:
        raise NotImplementedError("File download not supported for serverless provider. Results are returned as URLs.")


# asyncio imported at top of module
