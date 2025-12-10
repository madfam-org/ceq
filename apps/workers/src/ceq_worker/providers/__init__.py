"""
GPU Provider Abstraction Layer

Provides a unified interface for different GPU compute providers:
- Vast.ai (current)
- Furnace (future - via Enclii)
- RunPod (alternative)

This abstraction enables seamless migration between providers.
"""

from ceq_worker.providers.base import GPUProvider, ProviderConfig
from ceq_worker.providers.vast import VastAIProvider
from ceq_worker.providers.furnace import FurnaceProvider

__all__ = [
    "GPUProvider",
    "ProviderConfig",
    "VastAIProvider",
    "FurnaceProvider",
    "get_provider",
]


def get_provider(provider_type: str = "vast") -> GPUProvider:
    """
    Get the appropriate GPU provider instance.

    Args:
        provider_type: One of "vast", "furnace", "runpod"

    Returns:
        Configured GPUProvider instance
    """
    providers = {
        "vast": VastAIProvider,
        "furnace": FurnaceProvider,
        # "runpod": RunPodProvider,  # Future
    }

    if provider_type not in providers:
        raise ValueError(f"Unknown provider: {provider_type}. Available: {list(providers.keys())}")

    return providers[provider_type]()
