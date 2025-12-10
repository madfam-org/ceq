"""
Vast.ai GPU Provider Implementation

Implements the GPUProvider interface for Vast.ai marketplace.
https://vast.ai/docs/api

Vast.ai is a peer-to-peer GPU marketplace with competitive pricing
and wide GPU availability.
"""

import asyncio
import json
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


class VastAIProvider(GPUProvider):
    """
    Vast.ai GPU provider implementation.

    Uses the Vast.ai REST API for instance management.
    Supports Docker-based deployments with SSH access.
    """

    API_BASE = "https://console.vast.ai/api/v0"

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)
        self._client: httpx.AsyncClient | None = None

    def _load_config(self) -> ProviderConfig:
        """Load config from environment variables."""
        return ProviderConfig(
            api_key=os.getenv("VAST_API_KEY", ""),
            api_url=self.API_BASE,
            region=os.getenv("VAST_REGION", "any"),
            ssh_key_path=os.getenv("VAST_SSH_KEY", os.path.expanduser("~/.ssh/id_rsa")),
            default_image=os.getenv("VAST_DEFAULT_IMAGE", "ceq/worker:latest"),
            max_price_per_hour=float(os.getenv("VAST_MAX_PRICE", "1.0")),
            max_instances=int(os.getenv("VAST_MAX_INSTANCES", "5")),
            scale_to_zero=os.getenv("VAST_SCALE_TO_ZERO", "true").lower() == "true",
            idle_timeout_seconds=int(os.getenv("VAST_IDLE_TIMEOUT", "300")),
        )

    async def initialize(self) -> None:
        """Initialize Vast.ai client and validate API key."""
        if self._initialized:
            return

        if not self.config.api_key:
            raise ValueError("VAST_API_KEY environment variable required")

        self._client = httpx.AsyncClient(
            base_url=self.API_BASE,
            headers={"Authorization": f"Bearer {self.config.api_key}"},
            timeout=60.0,
        )

        # Validate API key by fetching account info
        response = await self._client.get("/users/current")
        if response.status_code != 200:
            raise ValueError(f"Invalid Vast.ai API key: {response.text}")

        user_data = response.json()
        print(f"   Vast.ai authenticated: {user_data.get('email', 'unknown')}")
        print(f"   Balance: ${user_data.get('balance', 0):.2f}")

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
            raise RuntimeError(f"Vast.ai API error: {response.status_code} - {response.text}")

        return response.json()

    # === Instance Lifecycle ===

    async def create_instance(self, spec: InstanceSpec) -> InstanceInfo:
        """Create a new Vast.ai instance."""
        # Find matching offer
        offers = await self._search_offers(spec)
        if not offers:
            raise RuntimeError(f"No available offers matching: {spec.gpu_type}")

        offer = offers[0]  # Best match (sorted by price)

        # Build create request
        create_data = {
            "client_id": "ceq-worker",
            "image": spec.image or self.config.default_image,
            "disk": spec.disk_gb,
            "runtype": "ssh",  # SSH + Docker
            "env": spec.env_vars,
            "onstart": self._generate_startup_script(spec),
            "label": json.dumps(spec.labels),
        }

        # Create instance from offer
        result = await self._request(
            "PUT",
            f"/asks/{offer['id']}/",
            json=create_data,
        )

        instance_id = str(result.get("new_contract"))

        # Wait for instance to be ready
        return await self._wait_for_ready(instance_id)

    async def _search_offers(self, spec: InstanceSpec) -> list[dict[str, Any]]:
        """Search for matching GPU offers."""
        # Map GPU type to Vast.ai query
        gpu_name = self._normalize_gpu_name(spec.gpu_type)

        query = {
            "gpu_name": {"eq": gpu_name},
            "num_gpus": {"gte": spec.gpu_count},
            "cpu_cores": {"gte": spec.cpu_cores},
            "cpu_ram": {"gte": spec.ram_gb * 1000},  # MB
            "disk_space": {"gte": spec.disk_gb},
            "verified": {"eq": True},
            "rentable": {"eq": True},
            "dph_total": {"lte": self.config.max_price_per_hour},
        }

        result = await self._request(
            "GET",
            "/bundles/",
            params={"q": json.dumps(query), "order": "dph_total"},
        )

        return result.get("offers", [])

    async def _wait_for_ready(
        self,
        instance_id: str,
        timeout: int = 300,
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

            await asyncio.sleep(5)

    async def start_instance(self, instance_id: str) -> InstanceInfo:
        """Start a stopped Vast.ai instance."""
        await self._request("PUT", f"/instances/{instance_id}/", json={"state": "running"})
        return await self._wait_for_ready(instance_id)

    async def stop_instance(self, instance_id: str) -> InstanceInfo:
        """Stop a running instance."""
        await self._request("PUT", f"/instances/{instance_id}/", json={"state": "stopped"})
        return await self.get_instance(instance_id)

    async def destroy_instance(self, instance_id: str) -> None:
        """Destroy an instance permanently."""
        await self._request("DELETE", f"/instances/{instance_id}/")

    async def get_instance(self, instance_id: str) -> InstanceInfo:
        """Get current instance information."""
        result = await self._request("GET", f"/instances/{instance_id}/")
        return self._parse_instance(result)

    async def list_instances(
        self,
        labels: dict[str, str] | None = None,
    ) -> list[InstanceInfo]:
        """List all instances, optionally filtered by labels."""
        result = await self._request("GET", "/instances/")
        instances = [self._parse_instance(inst) for inst in result.get("instances", [])]

        if labels:
            instances = [
                inst for inst in instances
                if all(inst.labels.get(k) == v for k, v in labels.items())
            ]

        return instances

    def _parse_instance(self, data: dict[str, Any]) -> InstanceInfo:
        """Parse Vast.ai instance data to InstanceInfo."""
        status_map = {
            "running": InstanceStatus.RUNNING,
            "loading": InstanceStatus.STARTING,
            "created": InstanceStatus.PENDING,
            "stopped": InstanceStatus.STOPPED,
            "destroying": InstanceStatus.STOPPING,
            "error": InstanceStatus.ERROR,
        }

        # Parse labels from JSON string
        labels = {}
        if label_str := data.get("label"):
            try:
                labels = json.loads(label_str)
            except json.JSONDecodeError:
                labels = {"name": label_str}

        return InstanceInfo(
            id=str(data.get("id")),
            provider="vast",
            status=status_map.get(data.get("actual_status", ""), InstanceStatus.PENDING),
            gpu_type=data.get("gpu_name", "unknown"),
            gpu_count=data.get("num_gpus", 1),
            public_ip=data.get("public_ipaddr"),
            ssh_port=data.get("ssh_port", 22),
            api_port=data.get("ports", {}).get("8188/tcp", [{}])[0].get("HostPort", 8188),
            price_per_hour=data.get("dph_total", 0),
            region=data.get("geolocation", ""),
            created_at=data.get("start_date", ""),
            labels=labels,
        )

    # === GPU Availability ===

    async def list_available_gpus(
        self,
        min_vram_gb: float = 0,
        max_price_per_hour: float | None = None,
        region: str | None = None,
    ) -> list[dict[str, Any]]:
        """List available GPU types and pricing."""
        query: dict[str, Any] = {
            "verified": {"eq": True},
            "rentable": {"eq": True},
        }

        if min_vram_gb > 0:
            query["gpu_ram"] = {"gte": min_vram_gb * 1000}  # MB

        if max_price_per_hour:
            query["dph_total"] = {"lte": max_price_per_hour}

        if region and region != "any":
            query["geolocation"] = {"eq": region}

        result = await self._request(
            "GET",
            "/bundles/",
            params={"q": json.dumps(query), "order": "dph_total", "limit": 100},
        )

        # Aggregate by GPU type
        gpu_types: dict[str, dict[str, Any]] = {}
        for offer in result.get("offers", []):
            gpu_name = offer.get("gpu_name", "unknown")
            if gpu_name not in gpu_types:
                gpu_types[gpu_name] = {
                    "gpu_type": gpu_name,
                    "vram_gb": offer.get("gpu_ram", 0) / 1000,
                    "price_per_hour": offer.get("dph_total", 0),
                    "available_count": 0,
                    "min_price": float("inf"),
                    "max_price": 0,
                }
            gpu_types[gpu_name]["available_count"] += 1
            price = offer.get("dph_total", 0)
            gpu_types[gpu_name]["min_price"] = min(gpu_types[gpu_name]["min_price"], price)
            gpu_types[gpu_name]["max_price"] = max(gpu_types[gpu_name]["max_price"], price)

        return list(gpu_types.values())

    async def find_cheapest_gpu(
        self,
        min_vram_gb: float = 16,
        gpu_tier: GPUTier | None = None,
    ) -> dict[str, Any] | None:
        """Find cheapest available GPU meeting requirements."""
        gpus = await self.list_available_gpus(
            min_vram_gb=min_vram_gb,
            max_price_per_hour=self.config.max_price_per_hour,
        )

        if not gpus:
            return None

        # Filter by tier if specified
        if gpu_tier:
            gpus = [
                g for g in gpus
                if self.gpu_tier_for_vram(g["vram_gb"]) == gpu_tier
            ]

        if not gpus:
            return None

        # Sort by price
        gpus.sort(key=lambda g: g["min_price"])
        return gpus[0]

    # === Health & Monitoring ===

    async def is_instance_healthy(self, instance_id: str) -> bool:
        """Check if instance is healthy and ComfyUI is responding."""
        try:
            info = await self.get_instance(instance_id)
            if info.status != InstanceStatus.RUNNING:
                return False

            if not info.public_ip:
                return False

            # Try to reach ComfyUI
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"http://{info.public_ip}:{info.api_port}/system_stats"
                )
                return response.status_code == 200

        except Exception:
            return False

    async def get_instance_logs(
        self,
        instance_id: str,
        tail: int = 100,
    ) -> str:
        """Get recent logs from instance."""
        result = await self._request(
            "GET",
            f"/instances/{instance_id}/logs/",
            params={"tail": tail},
        )
        return result.get("logs", "")

    async def get_usage_stats(self) -> dict[str, Any]:
        """Get account usage statistics."""
        result = await self._request("GET", "/users/current")
        instances = await self.list_instances()

        return {
            "total_spend": result.get("total_spent", 0),
            "balance": result.get("balance", 0),
            "active_instances": len([i for i in instances if i.status == InstanceStatus.RUNNING]),
            "total_instances": len(instances),
        }

    # === SSH/Exec ===

    async def ssh_command(
        self,
        instance_id: str,
        command: str,
        timeout: int = 60,
    ) -> tuple[str, str, int]:
        """Execute command via SSH."""
        info = await self.get_instance(instance_id)

        if not info.public_ip:
            raise RuntimeError(f"Instance {instance_id} has no public IP")

        ssh_cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", f"ConnectTimeout={timeout}",
            "-p", str(info.ssh_port),
            "-i", self.config.ssh_key_path,
            f"root@{info.public_ip}",
            command,
        ]

        proc = await asyncio.create_subprocess_exec(
            *ssh_cmd,
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
        """Upload file via SCP."""
        info = await self.get_instance(instance_id)

        if not info.public_ip:
            raise RuntimeError(f"Instance {instance_id} has no public IP")

        scp_cmd = [
            "scp",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-P", str(info.ssh_port),
            "-i", self.config.ssh_key_path,
            local_path,
            f"root@{info.public_ip}:{remote_path}",
        ]

        proc = await asyncio.create_subprocess_exec(*scp_cmd)
        await proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(f"SCP upload failed with code {proc.returncode}")

    async def download_file(
        self,
        instance_id: str,
        remote_path: str,
        local_path: str,
    ) -> None:
        """Download file via SCP."""
        info = await self.get_instance(instance_id)

        if not info.public_ip:
            raise RuntimeError(f"Instance {instance_id} has no public IP")

        scp_cmd = [
            "scp",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-P", str(info.ssh_port),
            "-i", self.config.ssh_key_path,
            f"root@{info.public_ip}:{remote_path}",
            local_path,
        ]

        proc = await asyncio.create_subprocess_exec(*scp_cmd)
        await proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(f"SCP download failed with code {proc.returncode}")

    # === Utilities ===

    def _normalize_gpu_name(self, gpu_type: str) -> str:
        """Normalize GPU type string to Vast.ai format."""
        gpu_map = {
            "RTX_4090": "RTX 4090",
            "RTX_3090": "RTX 3090",
            "RTX_3080": "RTX 3080",
            "A100_80GB": "A100 80GB",
            "A100_40GB": "A100",
            "A6000": "RTX A6000",
            "A5000": "RTX A5000",
            "H100": "H100",
        }
        return gpu_map.get(gpu_type, gpu_type)

    def _generate_startup_script(self, spec: InstanceSpec) -> str:
        """Generate instance startup script."""
        return """#!/bin/bash
set -e

# Pull and run CEQ worker
docker pull {image}
docker run -d \\
    --gpus all \\
    --name ceq-worker \\
    -p 8188:8188 \\
    -v /opt/models:/opt/models \\
    -v /opt/outputs:/opt/outputs \\
    {env_args} \\
    {image}

echo "CEQ worker started"
""".format(
            image=spec.image or self.config.default_image,
            env_args=" ".join(f"-e {k}={v}" for k, v in spec.env_vars.items()),
        )
