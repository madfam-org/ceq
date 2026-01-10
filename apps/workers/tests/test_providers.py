"""Tests for GPU providers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ceq_worker.providers.base import (
    GPUProvider,
    GPUTier,
    InstanceInfo,
    InstanceSpec,
    InstanceStatus,
    ProviderConfig,
)


class TestInstanceStatus:
    """Tests for InstanceStatus enum."""

    def test_status_values(self):
        """Should have all expected status values."""
        assert InstanceStatus.PENDING == "pending"
        assert InstanceStatus.STARTING == "starting"
        assert InstanceStatus.RUNNING == "running"
        assert InstanceStatus.STOPPING == "stopping"
        assert InstanceStatus.STOPPED == "stopped"
        assert InstanceStatus.ERROR == "error"

    def test_status_is_string(self):
        """Status values should be strings."""
        for status in InstanceStatus:
            assert isinstance(status.value, str)


class TestGPUTier:
    """Tests for GPUTier enum."""

    def test_tier_values(self):
        """Should have all expected tier values."""
        assert GPUTier.CONSUMER == "consumer"
        assert GPUTier.PROSUMER == "prosumer"
        assert GPUTier.DATACENTER == "datacenter"


class TestProviderConfig:
    """Tests for ProviderConfig dataclass."""

    def test_minimal_config(self):
        """Should create config with just API key."""
        config = ProviderConfig(api_key="test-key")
        assert config.api_key == "test-key"
        assert config.api_url == ""
        assert config.region == "us-east"

    def test_full_config(self):
        """Should accept all configuration options."""
        config = ProviderConfig(
            api_key="test-key",
            api_url="https://api.example.com",
            region="eu-west",
            ssh_key_path="/path/to/key",
            default_image="nvidia/cuda:12.0",
            max_price_per_hour=2.5,
            max_instances=10,
            scale_to_zero=False,
            idle_timeout_seconds=600,
        )
        assert config.max_price_per_hour == 2.5
        assert config.max_instances == 10
        assert config.scale_to_zero is False


class TestInstanceSpec:
    """Tests for InstanceSpec dataclass."""

    def test_minimal_spec(self):
        """Should create spec with just GPU type."""
        spec = InstanceSpec(gpu_type="RTX_4090")
        assert spec.gpu_type == "RTX_4090"
        assert spec.gpu_count == 1
        assert spec.cpu_cores == 8
        assert spec.ram_gb == 32
        assert spec.disk_gb == 100

    def test_full_spec(self):
        """Should accept all specification options."""
        spec = InstanceSpec(
            gpu_type="A100_80GB",
            gpu_count=4,
            cpu_cores=64,
            ram_gb=256,
            disk_gb=500,
            image="custom/image:latest",
            docker_args={"runtime": "nvidia"},
            env_vars={"CUDA_VISIBLE_DEVICES": "0,1,2,3"},
            expose_ports=[8188, 8080],
            labels={"project": "ceq", "env": "prod"},
        )
        assert spec.gpu_count == 4
        assert spec.expose_ports == [8188, 8080]
        assert spec.labels["project"] == "ceq"

    def test_default_ports(self):
        """Should expose ComfyUI port by default."""
        spec = InstanceSpec(gpu_type="RTX_4090")
        assert 8188 in spec.expose_ports


class TestInstanceInfo:
    """Tests for InstanceInfo dataclass."""

    def test_minimal_info(self):
        """Should create info with required fields."""
        info = InstanceInfo(
            id="instance-123",
            provider="vast",
            status=InstanceStatus.RUNNING,
            gpu_type="RTX_4090",
            gpu_count=1,
        )
        assert info.id == "instance-123"
        assert info.status == InstanceStatus.RUNNING
        assert info.public_ip is None

    def test_full_info(self):
        """Should accept all info fields."""
        info = InstanceInfo(
            id="instance-123",
            provider="vast",
            status=InstanceStatus.RUNNING,
            gpu_type="A100_80GB",
            gpu_count=2,
            public_ip="203.0.113.1",
            ssh_port=22,
            api_port=8188,
            price_per_hour=3.5,
            region="us-west",
            created_at="2025-01-01T00:00:00Z",
            labels={"job": "training"},
        )
        assert info.public_ip == "203.0.113.1"
        assert info.price_per_hour == 3.5


class TestGPUProviderBase:
    """Tests for GPUProvider base class utilities."""

    def test_gpu_tier_for_vram_consumer(self):
        """Should classify low VRAM as consumer tier."""
        # Create a mock provider to test utility methods
        class MockProvider(GPUProvider):
            def _load_config(self):
                return ProviderConfig(api_key="test")

            async def initialize(self): pass
            async def create_instance(self, spec): pass
            async def start_instance(self, id): pass
            async def stop_instance(self, id): pass
            async def destroy_instance(self, id): pass
            async def get_instance(self, id): pass
            async def list_instances(self, labels=None): pass
            async def list_available_gpus(self, **kwargs): pass
            async def find_cheapest_gpu(self, **kwargs): pass
            async def is_instance_healthy(self, id): pass
            async def get_instance_logs(self, id, tail=100): pass
            async def get_usage_stats(self): pass
            async def ssh_command(self, id, cmd, timeout=60): pass
            async def upload_file(self, id, local, remote): pass
            async def download_file(self, id, remote, local): pass

        provider = MockProvider()

        assert provider.gpu_tier_for_vram(10) == GPUTier.CONSUMER
        assert provider.gpu_tier_for_vram(16) == GPUTier.CONSUMER

    def test_gpu_tier_for_vram_prosumer(self):
        """Should classify medium VRAM as prosumer tier."""
        class MockProvider(GPUProvider):
            def _load_config(self):
                return ProviderConfig(api_key="test")

            async def initialize(self): pass
            async def create_instance(self, spec): pass
            async def start_instance(self, id): pass
            async def stop_instance(self, id): pass
            async def destroy_instance(self, id): pass
            async def get_instance(self, id): pass
            async def list_instances(self, labels=None): pass
            async def list_available_gpus(self, **kwargs): pass
            async def find_cheapest_gpu(self, **kwargs): pass
            async def is_instance_healthy(self, id): pass
            async def get_instance_logs(self, id, tail=100): pass
            async def get_usage_stats(self): pass
            async def ssh_command(self, id, cmd, timeout=60): pass
            async def upload_file(self, id, local, remote): pass
            async def download_file(self, id, remote, local): pass

        provider = MockProvider()

        assert provider.gpu_tier_for_vram(24) == GPUTier.PROSUMER
        assert provider.gpu_tier_for_vram(30) == GPUTier.PROSUMER

    def test_gpu_tier_for_vram_datacenter(self):
        """Should classify high VRAM as datacenter tier."""
        class MockProvider(GPUProvider):
            def _load_config(self):
                return ProviderConfig(api_key="test")

            async def initialize(self): pass
            async def create_instance(self, spec): pass
            async def start_instance(self, id): pass
            async def stop_instance(self, id): pass
            async def destroy_instance(self, id): pass
            async def get_instance(self, id): pass
            async def list_instances(self, labels=None): pass
            async def list_available_gpus(self, **kwargs): pass
            async def find_cheapest_gpu(self, **kwargs): pass
            async def is_instance_healthy(self, id): pass
            async def get_instance_logs(self, id, tail=100): pass
            async def get_usage_stats(self): pass
            async def ssh_command(self, id, cmd, timeout=60): pass
            async def upload_file(self, id, local, remote): pass
            async def download_file(self, id, remote, local): pass

        provider = MockProvider()

        assert provider.gpu_tier_for_vram(40) == GPUTier.DATACENTER
        assert provider.gpu_tier_for_vram(80) == GPUTier.DATACENTER

    def test_estimate_cost(self):
        """Should calculate cost correctly."""
        class MockProvider(GPUProvider):
            def _load_config(self):
                return ProviderConfig(api_key="test")

            async def initialize(self): pass
            async def create_instance(self, spec): pass
            async def start_instance(self, id): pass
            async def stop_instance(self, id): pass
            async def destroy_instance(self, id): pass
            async def get_instance(self, id): pass
            async def list_instances(self, labels=None): pass
            async def list_available_gpus(self, **kwargs): pass
            async def find_cheapest_gpu(self, **kwargs): pass
            async def is_instance_healthy(self, id): pass
            async def get_instance_logs(self, id, tail=100): pass
            async def get_usage_stats(self): pass
            async def ssh_command(self, id, cmd, timeout=60): pass
            async def upload_file(self, id, local, remote): pass
            async def download_file(self, id, remote, local): pass

        provider = MockProvider()

        # 2 hours at $1.50/hr = $3.00
        cost = provider.estimate_cost("RTX_4090", 2.0, 1.50)
        assert cost == 3.0

        # 0.5 hours at $3.00/hr = $1.50
        cost = provider.estimate_cost("A100", 0.5, 3.00)
        assert cost == 1.5


class TestVastAIProvider:
    """Tests for Vast.ai provider implementation."""

    @pytest.mark.asyncio
    async def test_vast_provider_imports(self):
        """Vast.ai provider should be importable."""
        from ceq_worker.providers.vast import VastAIProvider

        assert VastAIProvider is not None

    @pytest.mark.asyncio
    async def test_vast_provider_config_loading(self):
        """Vast.ai provider should load config from environment."""
        with patch.dict("os.environ", {
            "VAST_API_KEY": "test-vast-key",
        }):
            from ceq_worker.providers.vast import VastAIProvider

            # Provider should load config
            provider = VastAIProvider()
            assert provider.config is not None


class TestFurnaceProvider:
    """Tests for Furnace provider implementation."""

    @pytest.mark.asyncio
    async def test_furnace_provider_imports(self):
        """Furnace provider should be importable."""
        from ceq_worker.providers.furnace import FurnaceProvider

        assert FurnaceProvider is not None


class TestProviderFactory:
    """Tests for provider factory function."""

    def test_get_provider_vast(self):
        """Should return Vast.ai provider for 'vast' type."""
        from ceq_worker.providers import get_provider

        with patch.dict("os.environ", {"VAST_API_KEY": "test-key"}):
            provider = get_provider("vast")
            assert provider is not None
            assert "vast" in type(provider).__name__.lower()

    def test_get_provider_furnace(self):
        """Should return Furnace provider for 'furnace' type."""
        from ceq_worker.providers import get_provider

        provider = get_provider("furnace")
        assert provider is not None
        assert "furnace" in type(provider).__name__.lower()

    def test_get_provider_unknown(self):
        """Should raise error for unknown provider type."""
        from ceq_worker.providers import get_provider

        with pytest.raises((ValueError, KeyError)):
            get_provider("unknown_provider")
