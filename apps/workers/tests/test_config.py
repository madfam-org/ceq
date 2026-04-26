"""Tests for worker configuration."""

import os
import pytest
from unittest.mock import patch


class TestWorkerConfig:
    """Test worker configuration."""

    def test_default_config(self):
        """Test default configuration loads.

        CI sets REDIS_URL=redis://localhost:6379/0 in the workers job env;
        we must clear it (and any other test-time overrides) before
        instantiating Settings to assert the in-code default value of
        DB 14 per PORT_ALLOCATION.md.
        """
        from ceq_worker.config import Settings

        # Strip every env var that pydantic-settings would slurp into the
        # model — leave only what the test explicitly sets.
        env_overrides_to_clear = {
            "REDIS_URL": None,
            "WORKER_ID": None,
        }
        with patch.dict(
            os.environ,
            {k: v for k, v in env_overrides_to_clear.items() if v is not None},
            clear=False,
        ):
            for key in env_overrides_to_clear:
                os.environ.pop(key, None)
            settings = Settings()
            # Redis DB 14 per PORT_ALLOCATION.md
            assert "/14" in str(settings.redis_url)
            assert settings.worker_id is not None

    def test_redis_url_parsing(self):
        """Test Redis URL is properly configured."""
        from ceq_worker.config import Settings

        # Note: Settings uses RedisDsn validator which requires valid URL
        settings = Settings()
        assert "redis://" in str(settings.redis_url)

    def test_vast_provider_config(self):
        """Test Vast.ai provider configuration."""
        from ceq_worker.config import Settings

        with patch.dict(os.environ, {"VAST_API_KEY": "test-key-123"}):
            settings = Settings()
            assert settings.vast_api_key == "test-key-123"

    def test_r2_storage_config(self):
        """Test R2 storage configuration."""
        from ceq_worker.config import Settings

        with patch.dict(os.environ, {
            "R2_ENDPOINT": "https://r2.example.com",
            "R2_ACCESS_KEY": "test-access",
            "R2_SECRET_KEY": "test-secret",
            "R2_BUCKET": "test-bucket",
        }):
            settings = Settings()
            assert settings.r2_endpoint == "https://r2.example.com"
            assert settings.r2_bucket == "test-bucket"

    def test_paths_are_path_objects(self):
        """Test that path settings are Path objects."""
        from ceq_worker.config import Settings
        from pathlib import Path

        settings = Settings()
        assert isinstance(settings.comfyui_path, Path)
        assert isinstance(settings.models_path, Path)
        assert isinstance(settings.outputs_path, Path)
        assert isinstance(settings.cache_path, Path)

    def test_gpu_provider_default(self):
        """Test default GPU provider is vast."""
        from ceq_worker.config import Settings

        settings = Settings()
        assert settings.gpu_provider == "vast"

    def test_orchestrator_config(self):
        """Test orchestrator configuration settings."""
        from ceq_worker.config import Settings

        settings = Settings()
        assert settings.ceq_min_workers >= 0
        assert settings.ceq_max_workers > 0
        assert settings.ceq_idle_timeout > 0
        assert settings.ceq_max_hourly_spend > 0

    def test_get_settings_cached(self):
        """Test that get_settings returns cached instance."""
        from ceq_worker.config import get_settings

        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2
