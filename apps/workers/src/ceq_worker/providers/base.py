"""
Base GPU Provider Interface

Defines the abstract interface that all GPU providers must implement.
This enables provider-agnostic worker deployment and management.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InstanceStatus(str, Enum):
    """GPU instance lifecycle states."""
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class GPUTier(str, Enum):
    """GPU capability tiers for workload matching."""
    CONSUMER = "consumer"      # RTX 3080, 3090 - 10-24GB VRAM
    PROSUMER = "prosumer"      # RTX 4090, A5000 - 24GB VRAM
    DATACENTER = "datacenter"  # A100, H100 - 40-80GB VRAM


@dataclass
class ProviderConfig:
    """Configuration for GPU provider."""
    api_key: str
    api_url: str = ""
    region: str = "us-east"
    ssh_key_path: str = ""
    default_image: str = ""

    # Cost controls
    max_price_per_hour: float = 1.0
    max_instances: int = 5

    # Auto-scaling
    scale_to_zero: bool = True
    idle_timeout_seconds: int = 300


@dataclass
class InstanceSpec:
    """Specification for a GPU instance."""
    gpu_type: str  # e.g., "RTX_4090", "A100_80GB"
    gpu_count: int = 1
    cpu_cores: int = 8
    ram_gb: int = 32
    disk_gb: int = 100

    # Docker configuration
    image: str = ""
    docker_args: dict[str, Any] = field(default_factory=dict)
    env_vars: dict[str, str] = field(default_factory=dict)

    # Networking
    expose_ports: list[int] = field(default_factory=lambda: [8188])  # ComfyUI

    # Labels/Tags
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class InstanceInfo:
    """Information about a running GPU instance."""
    id: str
    provider: str
    status: InstanceStatus
    gpu_type: str
    gpu_count: int

    # Addressing
    public_ip: str | None = None
    ssh_port: int = 22
    api_port: int = 8188

    # Pricing
    price_per_hour: float = 0.0

    # Metadata
    region: str = ""
    created_at: str = ""
    labels: dict[str, str] = field(default_factory=dict)


class GPUProvider(ABC):
    """
    Abstract base class for GPU compute providers.

    Implementations must handle:
    - Instance lifecycle (create, start, stop, destroy)
    - SSH/API connectivity
    - Cost tracking
    - Health monitoring
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or self._load_config()
        self._initialized = False

    @abstractmethod
    def _load_config(self) -> ProviderConfig:
        """Load provider configuration from environment."""
        ...

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider (authenticate, validate config)."""
        ...

    # === Instance Lifecycle ===

    @abstractmethod
    async def create_instance(self, spec: InstanceSpec) -> InstanceInfo:
        """
        Create a new GPU instance.

        Args:
            spec: Instance specification

        Returns:
            Information about the created instance
        """
        ...

    @abstractmethod
    async def start_instance(self, instance_id: str) -> InstanceInfo:
        """Start a stopped instance."""
        ...

    @abstractmethod
    async def stop_instance(self, instance_id: str) -> InstanceInfo:
        """Stop a running instance (preserves state)."""
        ...

    @abstractmethod
    async def destroy_instance(self, instance_id: str) -> None:
        """Destroy an instance permanently."""
        ...

    @abstractmethod
    async def get_instance(self, instance_id: str) -> InstanceInfo:
        """Get current instance information."""
        ...

    @abstractmethod
    async def list_instances(
        self,
        labels: dict[str, str] | None = None,
    ) -> list[InstanceInfo]:
        """
        List instances, optionally filtered by labels.

        Args:
            labels: Filter instances by these labels

        Returns:
            List of matching instances
        """
        ...

    # === GPU Availability ===

    @abstractmethod
    async def list_available_gpus(
        self,
        min_vram_gb: float = 0,
        max_price_per_hour: float | None = None,
        region: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List available GPU types and their pricing.

        Returns list of dicts with keys:
        - gpu_type: str
        - vram_gb: float
        - price_per_hour: float
        - available_count: int
        - region: str
        """
        ...

    @abstractmethod
    async def find_cheapest_gpu(
        self,
        min_vram_gb: float = 16,
        gpu_tier: GPUTier | None = None,
    ) -> dict[str, Any] | None:
        """
        Find the cheapest available GPU meeting requirements.

        Args:
            min_vram_gb: Minimum VRAM required
            gpu_tier: Optional tier constraint

        Returns:
            GPU info dict or None if nothing available
        """
        ...

    # === Health & Monitoring ===

    @abstractmethod
    async def is_instance_healthy(self, instance_id: str) -> bool:
        """Check if instance is healthy and responding."""
        ...

    @abstractmethod
    async def get_instance_logs(
        self,
        instance_id: str,
        tail: int = 100,
    ) -> str:
        """Get recent logs from instance."""
        ...

    @abstractmethod
    async def get_usage_stats(self) -> dict[str, Any]:
        """
        Get usage statistics for the account.

        Returns dict with:
        - total_spend: float (current period)
        - active_instances: int
        - gpu_hours_used: float
        """
        ...

    # === SSH/Exec ===

    @abstractmethod
    async def ssh_command(
        self,
        instance_id: str,
        command: str,
        timeout: int = 60,
    ) -> tuple[str, str, int]:
        """
        Execute a command via SSH.

        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        ...

    @abstractmethod
    async def upload_file(
        self,
        instance_id: str,
        local_path: str,
        remote_path: str,
    ) -> None:
        """Upload a file to the instance via SCP."""
        ...

    @abstractmethod
    async def download_file(
        self,
        instance_id: str,
        remote_path: str,
        local_path: str,
    ) -> None:
        """Download a file from the instance via SCP."""
        ...

    # === Utilities ===

    def gpu_tier_for_vram(self, vram_gb: float) -> GPUTier:
        """Determine GPU tier from VRAM amount."""
        if vram_gb >= 40:
            return GPUTier.DATACENTER
        elif vram_gb >= 20:
            return GPUTier.PROSUMER
        return GPUTier.CONSUMER

    def estimate_cost(
        self,
        gpu_type: str,
        hours: float,
        price_per_hour: float,
    ) -> float:
        """Estimate cost for a GPU rental."""
        return hours * price_per_hour
