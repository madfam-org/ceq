"""
Model Cache Layer for CEQ Workers

Manages model downloads and caching from R2 storage with:
- LRU eviction based on disk usage
- Prefetching of commonly used models
- Background downloading for cold-start reduction
- Model affinity tracking for intelligent routing
"""

import asyncio
import contextlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import redis.asyncio as redis

from ceq_worker.config import get_settings
from ceq_worker.storage import StorageClient

settings = get_settings()


@dataclass
class CachedModel:
    """Metadata for a cached model."""

    name: str
    r2_uri: str
    local_path: Path
    size_bytes: int
    last_accessed: datetime
    access_count: int = 0
    model_type: str = "checkpoint"
    hash_sha256: str = ""


@dataclass
class CacheStats:
    """Cache statistics."""

    total_size_bytes: int = 0
    max_size_bytes: int = 50 * 1024**3  # 50GB default
    model_count: int = 0
    hit_count: int = 0
    miss_count: int = 0
    prefetch_pending: int = 0


class ModelCache:
    """
    Intelligent model cache for ComfyUI workers.

    Features:
    - LRU eviction when disk quota exceeded
    - Background prefetching based on queue analysis
    - Redis-based coordination across workers
    - Model affinity tracking for job routing
    """

    # Model types and their subdirectories
    MODEL_PATHS = {
        "checkpoint": "checkpoints",
        "lora": "loras",
        "vae": "vae",
        "clip": "clip",
        "controlnet": "controlnet",
        "upscale": "upscale_models",
        "embeddings": "embeddings",
        "ipadapter": "ipadapter",
    }

    # Known models with their R2 URIs (populated from templates)
    COMMON_MODELS = {
        "flux1-dev.safetensors": {
            "type": "checkpoint",
            "size_gb": 23.8,
            "r2_path": "models/checkpoints/flux1-dev.safetensors",
        },
        "flux1-schnell.safetensors": {
            "type": "checkpoint",
            "size_gb": 23.8,
            "r2_path": "models/checkpoints/flux1-schnell.safetensors",
        },
        "sd3_medium.safetensors": {
            "type": "checkpoint",
            "size_gb": 4.0,
            "r2_path": "models/checkpoints/sd3_medium.safetensors",
        },
        "sdxl_base.safetensors": {
            "type": "checkpoint",
            "size_gb": 6.94,
            "r2_path": "models/checkpoints/sdxl_base.safetensors",
        },
    }

    def __init__(
        self,
        cache_dir: Path | None = None,
        max_size_gb: float = 50.0,
    ) -> None:
        self.cache_dir = cache_dir or settings.models_path
        self.max_size_bytes = int(max_size_gb * 1024**3)

        self._storage = StorageClient()
        self._redis: redis.Redis | None = None
        self._models: dict[str, CachedModel] = {}
        self._stats = CacheStats(max_size_bytes=self.max_size_bytes)
        self._prefetch_task: asyncio.Task | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize cache and discover existing models."""
        if self._initialized:
            return

        print("📦 Initializing model cache...")
        print(f"   Cache dir: {self.cache_dir}")
        print(f"   Max size: {self.max_size_bytes / 1024**3:.1f} GB")

        # Ensure directories exist
        for subdir in self.MODEL_PATHS.values():
            (self.cache_dir / subdir).mkdir(parents=True, exist_ok=True)

        # Initialize storage client
        await self._storage.initialize()

        # Connect to Redis for coordination
        self._redis = redis.from_url(
            str(settings.redis_url),
            decode_responses=True,
        )

        # Discover existing cached models
        await self._scan_cache()

        # Start background prefetch task
        self._prefetch_task = asyncio.create_task(self._prefetch_loop())

        self._initialized = True
        print(f"   Cached models: {len(self._models)}")
        print(f"   Cache usage: {self._stats.total_size_bytes / 1024**3:.1f} GB")

    async def _scan_cache(self) -> None:
        """Scan cache directory for existing models."""
        for model_type, subdir in self.MODEL_PATHS.items():
            type_dir = self.cache_dir / subdir
            if not type_dir.exists():
                continue

            for model_path in type_dir.glob("*.safetensors"):
                size = model_path.stat().st_size
                mtime = datetime.fromtimestamp(model_path.stat().st_mtime)

                self._models[model_path.name] = CachedModel(
                    name=model_path.name,
                    r2_uri=f"r2://{settings.r2_bucket}/models/{subdir}/{model_path.name}",
                    local_path=model_path,
                    size_bytes=size,
                    last_accessed=mtime,
                    model_type=model_type,
                )
                self._stats.total_size_bytes += size
                self._stats.model_count += 1

            # Also scan .ckpt files
            for model_path in type_dir.glob("*.ckpt"):
                size = model_path.stat().st_size
                mtime = datetime.fromtimestamp(model_path.stat().st_mtime)

                self._models[model_path.name] = CachedModel(
                    name=model_path.name,
                    r2_uri=f"r2://{settings.r2_bucket}/models/{subdir}/{model_path.name}",
                    local_path=model_path,
                    size_bytes=size,
                    last_accessed=mtime,
                    model_type=model_type,
                )
                self._stats.total_size_bytes += size
                self._stats.model_count += 1

    async def get_model(self, model_name: str) -> Path | None:
        """
        Get a model path, downloading if necessary.

        Returns the local path to the model, or None if unavailable.
        """
        # Check if already cached
        if model_name in self._models:
            model = self._models[model_name]
            model.last_accessed = datetime.utcnow()
            model.access_count += 1
            self._stats.hit_count += 1

            # Update access time in Redis
            if self._redis:
                await self._redis.hset(
                    f"ceq:model:access:{model_name}",
                    mapping={
                        "last_accessed": model.last_accessed.isoformat(),
                        "access_count": str(model.access_count),
                    },
                )

            return model.local_path

        # Cache miss - need to download
        self._stats.miss_count += 1

        # Check if we know this model
        if model_name in self.COMMON_MODELS:
            model_info = self.COMMON_MODELS[model_name]
            return await self._download_model(
                model_name,
                f"r2://{settings.r2_bucket}/{model_info['r2_path']}",
                model_info["type"],
            )

        # Unknown model - check R2 directly
        return await self._discover_and_download(model_name)

    async def _download_model(
        self,
        model_name: str,
        r2_uri: str,
        model_type: str,
    ) -> Path | None:
        """Download a model from R2 storage."""
        # Ensure we have space
        estimated_size = self.COMMON_MODELS.get(model_name, {}).get("size_gb", 5.0) * 1024**3
        await self._ensure_space(int(estimated_size))

        # Determine local path
        subdir = self.MODEL_PATHS.get(model_type, "checkpoints")
        local_path = self.cache_dir / subdir / model_name

        print(f"📥 Downloading model: {model_name}")
        print(f"   From: {r2_uri}")
        print(f"   To: {local_path}")

        try:
            # Download from R2
            await self._storage.download_asset(r2_uri, local_path)

            # Register in cache
            size = local_path.stat().st_size
            self._models[model_name] = CachedModel(
                name=model_name,
                r2_uri=r2_uri,
                local_path=local_path,
                size_bytes=size,
                last_accessed=datetime.utcnow(),
                model_type=model_type,
            )
            self._stats.total_size_bytes += size
            self._stats.model_count += 1

            print(f"✅ Model cached: {model_name} ({size / 1024**3:.1f} GB)")
            return local_path

        except Exception as e:
            print(f"❌ Failed to download {model_name}: {e}")
            return None

    async def _discover_and_download(self, model_name: str) -> Path | None:
        """Try to find and download an unknown model."""
        # Check Redis for model location hints
        if self._redis:
            hint = await self._redis.hget("ceq:model:locations", model_name)
            if hint:
                return await self._download_model(model_name, hint, "checkpoint")

        # Try common paths
        for model_type, subdir in self.MODEL_PATHS.items():
            r2_uri = f"r2://{settings.r2_bucket}/models/{subdir}/{model_name}"
            try:
                # Quick existence check would go here
                # For now, attempt download
                result = await self._download_model(model_name, r2_uri, model_type)
                if result:
                    return result
            except Exception:
                continue

        return None

    async def _ensure_space(self, needed_bytes: int) -> None:
        """Ensure enough space is available, evicting if necessary."""
        available = self.max_size_bytes - self._stats.total_size_bytes

        if available >= needed_bytes:
            return

        # Need to evict - sort by LRU
        models_by_access = sorted(
            self._models.values(),
            key=lambda m: m.last_accessed,
        )

        bytes_freed = 0
        for model in models_by_access:
            if available + bytes_freed >= needed_bytes:
                break

            # Evict this model
            await self._evict_model(model.name)
            bytes_freed += model.size_bytes

    async def _evict_model(self, model_name: str) -> None:
        """Remove a model from cache."""
        if model_name not in self._models:
            return

        model = self._models[model_name]
        print(f"🗑️ Evicting model: {model_name}")

        try:
            if model.local_path.exists():
                model.local_path.unlink()
        except Exception as e:
            print(f"⚠️ Failed to delete {model_name}: {e}")
            return

        self._stats.total_size_bytes -= model.size_bytes
        self._stats.model_count -= 1
        del self._models[model_name]

    async def _prefetch_loop(self) -> None:
        """Background task to prefetch models based on queue analysis."""
        while True:
            try:
                await self._analyze_and_prefetch()
            except Exception as e:
                print(f"⚠️ Prefetch error: {e}")

            # Check every 60 seconds
            await asyncio.sleep(60)

    async def _analyze_and_prefetch(self) -> None:
        """Analyze pending jobs and prefetch needed models."""
        if not self._redis:
            return

        # Get pending jobs
        pending = await self._redis.lrange(settings.job_queue_key, 0, 10)

        models_needed: set[str] = set()
        for job_data in pending:
            try:
                job = json.loads(job_data)
                workflow = job.get("input", {}).get("workflow_json", {})

                # Extract model references from workflow nodes
                for _node_id, node in workflow.items():
                    if isinstance(node, dict):
                        inputs = node.get("inputs", {})
                        for key, value in inputs.items():
                            if key in ("ckpt_name", "model_name", "lora_name") and isinstance(value, str):
                                models_needed.add(value)
            except Exception:
                continue

        # Prefetch models we don't have
        for model_name in models_needed:
            if model_name not in self._models:
                self._stats.prefetch_pending += 1
                asyncio.create_task(self._prefetch_model(model_name))

    async def _prefetch_model(self, model_name: str) -> None:
        """Background prefetch a single model."""
        try:
            await self.get_model(model_name)
        finally:
            self._stats.prefetch_pending -= 1

    async def get_models_for_workflow(
        self,
        workflow: dict[str, Any],
    ) -> list[str]:
        """
        Analyze a workflow and return list of required models.

        Used for:
        - Job routing to workers with cached models
        - Prefetch planning
        - Cost estimation
        """
        models: list[str] = []

        for _node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue

            inputs = node.get("inputs", {})

            # Checkpoint loaders
            if ckpt := inputs.get("ckpt_name"):
                models.append(ckpt)
            if model := inputs.get("model_name"):
                models.append(model)

            # LoRA loaders
            if lora := inputs.get("lora_name"):
                models.append(lora)

            # VAE
            if vae := inputs.get("vae_name"):
                models.append(vae)

            # ControlNet
            if controlnet := inputs.get("control_net_name"):
                models.append(controlnet)

        return list(set(models))

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "total_size_gb": self._stats.total_size_bytes / 1024**3,
            "max_size_gb": self._stats.max_size_bytes / 1024**3,
            "model_count": self._stats.model_count,
            "hit_rate": (
                self._stats.hit_count / max(1, self._stats.hit_count + self._stats.miss_count)
            ),
            "hits": self._stats.hit_count,
            "misses": self._stats.miss_count,
            "prefetch_pending": self._stats.prefetch_pending,
            "models": list(self._models.keys()),
        }

    async def get_worker_affinity(self) -> list[str]:
        """
        Get list of models this worker has cached.

        Used by orchestrator for intelligent job routing.
        """
        return list(self._models.keys())

    async def register_affinity(self, worker_id: str) -> None:
        """Register this worker's model affinity in Redis."""
        if not self._redis:
            return

        models = list(self._models.keys())
        await self._redis.hset(
            "ceq:worker:affinity",
            worker_id,
            json.dumps(models),
        )

    async def shutdown(self) -> None:
        """Shutdown cache manager."""
        if self._prefetch_task:
            self._prefetch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._prefetch_task

        if self._redis:
            await self._redis.close()
