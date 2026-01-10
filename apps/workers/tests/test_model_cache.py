"""Tests for model caching."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestModelCache:
    """Test model caching functionality."""

    def test_cache_initialization(self):
        """Test cache initializes correctly."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(
            cache_dir=Path("/tmp/models"),
            max_size_gb=50,
        )

        assert cache.cache_dir == Path("/tmp/models")
        assert cache.max_size_bytes == 50 * 1024**3

    def test_cache_default_size(self):
        """Test cache default max size is 50GB."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(cache_dir=Path("/tmp/models"))

        assert cache.max_size_bytes == 50 * 1024**3

    def test_model_paths_constant(self):
        """Test MODEL_PATHS constant has expected types."""
        from ceq_worker.model_cache import ModelCache

        expected_types = ["checkpoint", "lora", "vae", "clip", "controlnet"]
        for model_type in expected_types:
            assert model_type in ModelCache.MODEL_PATHS

    def test_common_models_constant(self):
        """Test COMMON_MODELS has flux models."""
        from ceq_worker.model_cache import ModelCache

        assert "flux1-dev.safetensors" in ModelCache.COMMON_MODELS
        assert "flux1-schnell.safetensors" in ModelCache.COMMON_MODELS

    def test_internal_state(self):
        """Test cache internal state after init."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(cache_dir=Path("/tmp/models"))

        assert cache._models == {}
        assert cache._initialized is False
        assert cache._redis is None


class TestModelDownload:
    """Test model downloading."""

    @pytest.mark.asyncio
    async def test_get_model_cached(self):
        """Test get_model returns path when model is cached."""
        from ceq_worker.model_cache import ModelCache, CachedModel
        from datetime import datetime

        cache = ModelCache(cache_dir=Path("/tmp/models"))

        # Pre-populate cache
        cache._models["test_model.safetensors"] = CachedModel(
            name="test_model.safetensors",
            r2_uri="r2://bucket/path",
            local_path=Path("/tmp/models/checkpoints/test_model.safetensors"),
            size_bytes=1024,
            last_accessed=datetime.utcnow(),
        )
        cache._redis = AsyncMock()

        result = await cache.get_model("test_model.safetensors")

        assert result == Path("/tmp/models/checkpoints/test_model.safetensors")
        assert cache._stats.hit_count == 1

    @pytest.mark.asyncio
    async def test_get_model_miss(self):
        """Test get_model attempts download on cache miss."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(cache_dir=Path("/tmp/models"))

        # Mock _download_model to avoid actual download
        cache._download_model = AsyncMock(return_value=None)
        cache._discover_and_download = AsyncMock(return_value=None)

        result = await cache.get_model("nonexistent.safetensors")

        assert result is None
        assert cache._stats.miss_count == 1

    @pytest.mark.asyncio
    async def test_get_model_known_model(self):
        """Test get_model downloads known models."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(cache_dir=Path("/tmp/models"))

        # Mock download
        expected_path = Path("/tmp/models/checkpoints/flux1-dev.safetensors")
        cache._download_model = AsyncMock(return_value=expected_path)

        result = await cache.get_model("flux1-dev.safetensors")

        assert result == expected_path
        cache._download_model.assert_called_once()


class TestCacheEviction:
    """Test cache eviction (LRU)."""

    def test_has_lru_tracking(self):
        """Test cache has LRU tracking via _models dict."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(
            cache_dir=Path("/tmp/models"),
            max_size_gb=1,
        )

        # _models dict is used for LRU tracking
        assert hasattr(cache, "_models")
        assert isinstance(cache._models, dict)

    @pytest.mark.asyncio
    async def test_ensure_space_triggers_eviction(self):
        """Test _ensure_space evicts old models when needed."""
        from ceq_worker.model_cache import ModelCache, CachedModel
        from datetime import datetime, timedelta

        cache = ModelCache(
            cache_dir=Path("/tmp/models"),
            max_size_gb=0.001,  # Very small: ~1MB
        )

        # Add an old model
        old_model_path = Path("/tmp/old_model.safetensors")
        cache._models["old_model.safetensors"] = CachedModel(
            name="old_model.safetensors",
            r2_uri="r2://bucket/old",
            local_path=old_model_path,
            size_bytes=500000,  # 500KB
            last_accessed=datetime.utcnow() - timedelta(days=7),
        )
        cache._stats.total_size_bytes = 500000

        # Mock eviction
        cache._evict_model = AsyncMock()

        # Request space for 1MB
        await cache._ensure_space(1000000)

        # Should have called eviction
        cache._evict_model.assert_called_once_with("old_model.safetensors")

    def test_cache_stats_tracking(self):
        """Test cache size is tracked in stats."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(cache_dir=Path("/tmp/models"), max_size_gb=50)

        # Stats should track size
        assert hasattr(cache._stats, "total_size_bytes")
        assert hasattr(cache._stats, "max_size_bytes")
        assert hasattr(cache._stats, "model_count")


class TestCacheStats:
    """Test cache statistics."""

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test get_stats returns expected fields."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(cache_dir=Path("/tmp/models"))

        stats = await cache.get_stats()

        assert "total_size_gb" in stats
        assert "max_size_gb" in stats
        assert "model_count" in stats
        assert "hit_rate" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "models" in stats


class TestWorkflowAnalysis:
    """Test workflow model extraction."""

    @pytest.mark.asyncio
    async def test_get_models_for_workflow(self):
        """Test extracting model requirements from workflow."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(cache_dir=Path("/tmp/models"))

        workflow = {
            "4": {
                "inputs": {
                    "ckpt_name": "flux1-dev.safetensors",
                }
            },
            "10": {
                "inputs": {
                    "lora_name": "detail-enhancer.safetensors",
                }
            }
        }

        models = await cache.get_models_for_workflow(workflow)

        assert "flux1-dev.safetensors" in models
        assert "detail-enhancer.safetensors" in models

    @pytest.mark.asyncio
    async def test_get_models_for_workflow_empty(self):
        """Test empty workflow returns empty list."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(cache_dir=Path("/tmp/models"))

        models = await cache.get_models_for_workflow({})

        assert models == []


class TestWorkerAffinity:
    """Test worker model affinity."""

    @pytest.mark.asyncio
    async def test_get_worker_affinity(self):
        """Test getting worker's cached models for affinity."""
        from ceq_worker.model_cache import ModelCache, CachedModel
        from datetime import datetime

        cache = ModelCache(cache_dir=Path("/tmp/models"))

        cache._models["model1.safetensors"] = CachedModel(
            name="model1.safetensors",
            r2_uri="r2://bucket/model1",
            local_path=Path("/tmp/model1.safetensors"),
            size_bytes=1024,
            last_accessed=datetime.utcnow(),
        )
        cache._models["model2.safetensors"] = CachedModel(
            name="model2.safetensors",
            r2_uri="r2://bucket/model2",
            local_path=Path("/tmp/model2.safetensors"),
            size_bytes=2048,
            last_accessed=datetime.utcnow(),
        )

        affinity = await cache.get_worker_affinity()

        assert "model1.safetensors" in affinity
        assert "model2.safetensors" in affinity

    @pytest.mark.asyncio
    async def test_register_affinity(self):
        """Test registering affinity to Redis."""
        from ceq_worker.model_cache import ModelCache, CachedModel
        from datetime import datetime

        cache = ModelCache(cache_dir=Path("/tmp/models"))
        cache._redis = AsyncMock()

        cache._models["model1.safetensors"] = CachedModel(
            name="model1.safetensors",
            r2_uri="r2://bucket/model1",
            local_path=Path("/tmp/model1.safetensors"),
            size_bytes=1024,
            last_accessed=datetime.utcnow(),
        )

        await cache.register_affinity("worker-1")

        cache._redis.hset.assert_called_once()


class TestCacheLifecycle:
    """Test cache lifecycle management."""

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test shutdown cleans up resources."""
        from ceq_worker.model_cache import ModelCache
        import asyncio

        cache = ModelCache(cache_dir=Path("/tmp/models"))
        cache._redis = AsyncMock()
        cache._prefetch_task = asyncio.create_task(asyncio.sleep(1000))

        await cache.shutdown()

        cache._redis.close.assert_called_once()
        assert cache._prefetch_task.cancelled()
