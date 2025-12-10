"""
Furnace GPU Provider Implementation (Enclii Internal)

Implements the GPUProvider interface for the internal Furnace
GPU infrastructure running within Enclii.

This is the future migration target from Vast.ai - provides
similar capabilities but with tighter Enclii integration,
better cost control, and internal billing via Waybill.

API Endpoints (planned - ports 4210-4215):
- furnace-gateway: 4210 (API gateway)
- furnace-scheduler: 4211 (job scheduling)
- furnace-registry: 4212 (model/template registry)
- furnace-metrics: 4213 (monitoring)
"""

import asyncio
import os
from typing import Any

import httpx

from ceq_worker.providers.base import (
    GPUProvider,
    GPUTier,
    InstanceInfo,
    InstanceSpec,
    InstanceStatus,
    ProviderConfig,
)


class FurnaceProvider(GPUProvider):
    """
    Furnace GPU provider for Enclii internal infrastructure.

    Uses the Furnace API (part of Enclii) for GPU instance management.
    Integrates with:
    - Switchyard for deployment orchestration
    - Waybill for GPU usage billing
    - KEDA for scale-to-zero
    """

    def _load_config(self) -> ProviderConfig:
        """Load config from environment variables."""
        return ProviderConfig(
            api_key=os.getenv("FURNACE_API_KEY", ""),
            api_url=os.getenv("FURNACE_API_URL", "http://furnace-gateway:4210"),
            region=os.getenv("FURNACE_REGION", "hetzner-fsn1"),
            ssh_key_path=os.getenv("FURNACE_SSH_KEY", os.path.expanduser("~/.ssh/id_rsa")),
            default_image=os.getenv("FURNACE_DEFAULT_IMAGE", "ghcr.io/madfam/ceq-worker:latest"),
            max_price_per_hour=float(os.getenv("FURNACE_MAX_PRICE", "0.50")),
            max_instances=int(os.getenv("FURNACE_MAX_INSTANCES", "10")),
            scale_to_zero=os.getenv("FURNACE_SCALE_TO_ZERO", "true").lower() == "true",
            idle_timeout_seconds=int(os.getenv("FURNACE_IDLE_TIMEOUT", "300")),
        )

    async def initialize(self) -> None:
        """Initialize Furnace client."""
        if self._initialized:
            return

        self._client = httpx.AsyncClient(
            base_url=self.config.api_url,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "X-Provider": "furnace",
            },
            timeout=60.0,
        )

        # Validate connection to Furnace gateway
        try:
            response = await self._client.get("/health")
            if response.status_code != 200:
                raise ValueError(f"Furnace gateway unhealthy: {response.text}")

            health = response.json()
            print(f"   Furnace connected: {self.config.api_url}")
            print(f"   Status: {health.get('status', 'unknown')}")
            print(f"   GPU pool: {health.get('available_gpus', 0)} available")

        except httpx.ConnectError:
            # Furnace not yet deployed - this is expected during development
            print("   ⚠️ Furnace gateway not available (development mode)")
            print("   Furnace will be available after Enclii GPU infrastructure deployment")
            # Don't raise - allow initialization to complete for stub mode

        self._initialized = True

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make authenticated API request."""
        if not self._client:
            raise RuntimeError("Provider not initialized")

        response = await self._client.request(method, path, **kwargs)

        if response.status_code >= 400:
            raise RuntimeError(f"Furnace API error: {response.status_code} - {response.text}")

        return response.json()

    # === Instance Lifecycle ===

    async def create_instance(self, spec: InstanceSpec) -> InstanceInfo:
        """Create a new Furnace GPU worker instance."""
        create_data = {
            "gpu_type": spec.gpu_type,
            "gpu_count": spec.gpu_count,
            "image": spec.image or self.config.default_image,
            "disk_gb": spec.disk_gb,
            "env": spec.env_vars,
            "labels": spec.labels,
            "ports": spec.expose_ports,
            "scale_to_zero": self.config.scale_to_zero,
            "idle_timeout": self.config.idle_timeout_seconds,
        }

        result = await self._request("POST", "/instances", json=create_data)
        instance_id = result.get("id")

        return await self._wait_for_ready(instance_id)

    async def _wait_for_ready(
        self,
        instance_id: str,
        timeout: int = 120,  # Faster than Vast.ai due to pre-warmed pods
    ) -> InstanceInfo:
        """Wait for instance to reach running state."""
        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Instance {instance_id} failed to start within {timeout}s")

            info = await self.get_instance(instance_id)
            if info.status == InstanceStatus.RUNNING and info.public_ip:
                return info

            if info.status == InstanceStatus.ERROR:
                raise RuntimeError(f"Instance {instance_id} failed to start")

            await asyncio.sleep(2)  # Faster polling for internal infra

    async def start_instance(self, instance_id: str) -> InstanceInfo:
        """Start a stopped instance (scale from zero)."""
        await self._request("POST", f"/instances/{instance_id}/start")
        return await self._wait_for_ready(instance_id)

    async def stop_instance(self, instance_id: str) -> InstanceInfo:
        """Stop a running instance (scale to zero)."""
        await self._request("POST", f"/instances/{instance_id}/stop")
        return await self.get_instance(instance_id)

    async def destroy_instance(self, instance_id: str) -> None:
        """Destroy an instance permanently."""
        await self._request("DELETE", f"/instances/{instance_id}")

    async def get_instance(self, instance_id: str) -> InstanceInfo:
        """Get current instance information."""
        result = await self._request("GET", f"/instances/{instance_id}")
        return self._parse_instance(result)

    async def list_instances(
        self,
        labels: dict[str, str] | None = None,
    ) -> list[InstanceInfo]:
        """List instances filtered by labels."""
        params = {}
        if labels:
            params["labels"] = ",".join(f"{k}={v}" for k, v in labels.items())

        result = await self._request("GET", "/instances", params=params)
        return [self._parse_instance(inst) for inst in result.get("instances", [])]

    def _parse_instance(self, data: dict[str, Any]) -> InstanceInfo:
        """Parse Furnace instance data to InstanceInfo."""
        status_map = {
            "running": InstanceStatus.RUNNING,
            "starting": InstanceStatus.STARTING,
            "pending": InstanceStatus.PENDING,
            "stopped": InstanceStatus.STOPPED,
            "stopping": InstanceStatus.STOPPING,
            "error": InstanceStatus.ERROR,
        }

        return InstanceInfo(
            id=data.get("id", ""),
            provider="furnace",
            status=status_map.get(data.get("status", ""), InstanceStatus.PENDING),
            gpu_type=data.get("gpu_type", "unknown"),
            gpu_count=data.get("gpu_count", 1),
            public_ip=data.get("endpoint", {}).get("host"),
            ssh_port=data.get("endpoint", {}).get("ssh_port", 22),
            api_port=data.get("endpoint", {}).get("api_port", 8188),
            price_per_hour=data.get("price_per_hour", 0),
            region=data.get("region", self.config.region),
            created_at=data.get("created_at", ""),
            labels=data.get("labels", {}),
        )

    # === GPU Availability ===

    async def list_available_gpus(
        self,
        min_vram_gb: float = 0,
        max_price_per_hour: float | None = None,
        region: str | None = None,
    ) -> list[dict[str, Any]]:
        """List available GPU types in Furnace pool."""
        params: dict[str, Any] = {}

        if min_vram_gb > 0:
            params["min_vram_gb"] = min_vram_gb
        if max_price_per_hour:
            params["max_price"] = max_price_per_hour
        if region:
            params["region"] = region

        result = await self._request("GET", "/gpus", params=params)
        return result.get("gpus", [])

    async def find_cheapest_gpu(
        self,
        min_vram_gb: float = 16,
        gpu_tier: GPUTier | None = None,
    ) -> dict[str, Any] | None:
        """Find cheapest available GPU in Furnace pool."""
        gpus = await self.list_available_gpus(
            min_vram_gb=min_vram_gb,
            max_price_per_hour=self.config.max_price_per_hour,
        )

        if not gpus:
            return None

        if gpu_tier:
            gpus = [
                g for g in gpus
                if self.gpu_tier_for_vram(g.get("vram_gb", 0)) == gpu_tier
            ]

        if not gpus:
            return None

        gpus.sort(key=lambda g: g.get("price_per_hour", float("inf")))
        return gpus[0]

    # === Health & Monitoring ===

    async def is_instance_healthy(self, instance_id: str) -> bool:
        """Check if instance is healthy via Furnace health probes."""
        try:
            result = await self._request("GET", f"/instances/{instance_id}/health")
            return result.get("healthy", False)
        except Exception:
            return False

    async def get_instance_logs(
        self,
        instance_id: str,
        tail: int = 100,
    ) -> str:
        """Get logs from Furnace (via Signal integration)."""
        result = await self._request(
            "GET",
            f"/instances/{instance_id}/logs",
            params={"tail": tail},
        )
        return result.get("logs", "")

    async def get_usage_stats(self) -> dict[str, Any]:
        """Get usage stats from Waybill integration."""
        result = await self._request("GET", "/usage")
        return {
            "total_spend": result.get("gpu_cost_total", 0),
            "gpu_hours_used": result.get("gpu_hours", 0),
            "active_instances": result.get("active_instances", 0),
            "billing_period": result.get("billing_period", ""),
        }

    # === SSH/Exec (via kubectl exec for K8s pods) ===

    async def ssh_command(
        self,
        instance_id: str,
        command: str,
        timeout: int = 60,
    ) -> tuple[str, str, int]:
        """Execute command in Furnace instance via kubectl exec."""
        # Furnace uses K8s pods - use kubectl exec instead of SSH
        info = await self.get_instance(instance_id)

        kubectl_cmd = [
            "kubectl",
            "exec",
            "-n", "ceq-workers",
            f"pod/{info.id}",
            "--",
            "sh", "-c", command,
        ]

        proc = await asyncio.create_subprocess_exec(
            *kubectl_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode(), stderr.decode(), proc.returncode or 0

    async def upload_file(
        self,
        instance_id: str,
        local_path: str,
        remote_path: str,
    ) -> None:
        """Upload file to Furnace instance via kubectl cp."""
        info = await self.get_instance(instance_id)

        kubectl_cmd = [
            "kubectl",
            "cp",
            "-n", "ceq-workers",
            local_path,
            f"{info.id}:{remote_path}",
        ]

        proc = await asyncio.create_subprocess_exec(*kubectl_cmd)
        await proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(f"kubectl cp failed with code {proc.returncode}")

    async def download_file(
        self,
        instance_id: str,
        remote_path: str,
        local_path: str,
    ) -> None:
        """Download file from Furnace instance via kubectl cp."""
        info = await self.get_instance(instance_id)

        kubectl_cmd = [
            "kubectl",
            "cp",
            "-n", "ceq-workers",
            f"{info.id}:{remote_path}",
            local_path,
        ]

        proc = await asyncio.create_subprocess_exec(*kubectl_cmd)
        await proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(f"kubectl cp failed with code {proc.returncode}")
