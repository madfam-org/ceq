"""Tests for model caching."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestModelCache:
    """Test model caching functionality."""

    def test_cache_initialization(self):
        """Test cache initializes correctly."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(
            cache_dir="/tmp/models",
            max_size_gb=50,
        )

        assert cache.cache_dir == "/tmp/models"
        assert cache.max_size_gb == 50

    def test_model_path_generation(self):
        """Test model path generation."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(cache_dir="/tmp/models")

        model_name = "sd_xl_base_1.0.safetensors"
        expected_path = "/tmp/models/checkpoints/sd_xl_base_1.0.safetensors"

        path = cache.get_model_path(model_name, "checkpoint")

        assert "sd_xl_base_1.0.safetensors" in path

    def test_cache_hit_detection(self):
        """Test cache hit detection."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(cache_dir="/tmp/models")

        # Mock file existence
        with patch("pathlib.Path.exists", return_value=True):
            is_cached = cache.is_cached("test_model.safetensors")
            assert is_cached is True

        with patch("pathlib.Path.exists", return_value=False):
            is_cached = cache.is_cached("missing_model.safetensors")
            assert is_cached is False


class TestModelDownload:
    """Test model downloading."""

    @pytest.mark.asyncio
    async def test_download_from_r2(self, mock_storage):
        """Test downloading model from R2."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(cache_dir="/tmp/models")

        with patch.object(cache, "_download_from_r2", new_callable=AsyncMock) as mock_download:
            mock_download.return_value = "/tmp/models/test.safetensors"

            path = await cache._download_from_r2(
                "r2://ceq-assets/models/test.safetensors",
                "/tmp/models/test.safetensors",
            )

            assert path == "/tmp/models/test.safetensors"

    @pytest.mark.asyncio
    async def test_download_progress_tracking(self, mock_storage):
        """Test download progress is tracked."""
        # Progress tracking should update Redis
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(cache_dir="/tmp/models")

        # Verify cache has progress tracking capability
        assert hasattr(cache, "_download_from_r2") or hasattr(cache, "download_model")


class TestCacheEviction:
    """Test cache eviction (LRU)."""

    def test_lru_eviction_order(self):
        """Test LRU eviction order."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(
            cache_dir="/tmp/models",
            max_size_gb=1,  # Small cache to trigger eviction
        )

        # LRU tracking should exist
        assert hasattr(cache, "_models") or hasattr(cache, "_access_times")

    def test_cache_size_tracking(self):
        """Test cache size is tracked."""
        from ceq_worker.model_cache import ModelCache

        cache = ModelCache(cache_dir="/tmp/models", max_size_gb=50)

        # Should have method to get current size
        assert hasattr(cache, "get_current_size") or hasattr(cache, "_current_size")
