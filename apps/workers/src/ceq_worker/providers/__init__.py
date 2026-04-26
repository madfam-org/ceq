"""
GPU Provider Abstraction Layer

Provides a unified interface for different GPU compute providers:
- Vast.ai (current) — P2P GPU marketplace, Docker-based instances
- fal.ai (current) — Serverless API, per-request billing, fast image gen
- Furnace (future - via Enclii) — Self-hosted GPU scheduling

This abstraction enables seamless migration between providers.
"""

from ceq_worker.providers.base import GPUProvider, ProviderConfig
from ceq_worker.providers.fal import FalAIProvider
from ceq_worker.providers.furnace import FurnaceProvider
from ceq_worker.providers.vast import VastAIProvider

__all__ = [
    "GPUProvider",
    "ProviderConfig",
    "VastAIProvider",
    "FurnaceProvider",
    "FalAIProvider",
    "get_provider",
]


def get_provider(provider_type: str = "vast") -> GPUProvider:
    """
    Get the appropriate GPU provider instance.

    Args:
        provider_type: One of "vast", "fal", "furnace"

    Returns:
        Configured GPUProvider instance
    """
    providers = {
        "vast": VastAIProvider,
        "fal": FalAIProvider,
        "furnace": FurnaceProvider,
    }

    if provider_type not in providers:
        raise ValueError(f"Unknown provider: {provider_type}. Available: {list(providers.keys())}")

    return providers[provider_type]()
