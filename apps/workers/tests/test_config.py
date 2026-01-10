"""Tests for worker configuration."""

import os
import pytest
from unittest.mock import patch


class TestWorkerConfig:
    """Test worker configuration."""

    def test_default_config(self):
        """Test default configuration loads."""
        from ceq_worker.config import WorkerSettings

        with patch.dict(os.environ, {}, clear=True):
            settings = WorkerSettings()
            assert settings.redis_db == 14
            assert settings.worker_id is not None

    def test_redis_url_parsing(self):
        """Test Redis URL is properly configured."""
        from ceq_worker.config import WorkerSettings

        settings = WorkerSettings(
            redis_url="redis://:password@localhost:6379/14"
        )
        assert "redis://" in str(settings.redis_url)

    def test_vast_provider_config(self):
        """Test Vast.ai provider configuration."""
        from ceq_worker.config import WorkerSettings

        settings = WorkerSettings(
            vast_api_key="test-key-123"
        )
        assert settings.vast_api_key == "test-key-123"

    def test_r2_storage_config(self):
        """Test R2 storage configuration."""
        from ceq_worker.config import WorkerSettings

        settings = WorkerSettings(
            r2_endpoint="https://r2.example.com",
            r2_access_key="test-access",
            r2_secret_key="test-secret",
            r2_bucket="test-bucket",
        )
        assert settings.r2_endpoint == "https://r2.example.com"
        assert settings.r2_bucket == "test-bucket"
