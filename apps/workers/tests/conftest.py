"""Pytest fixtures for CEQ Worker tests."""

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.lpush.return_value = None
    redis.rpop.return_value = None
    redis.brpop.return_value = None
    redis.hset.return_value = None
    redis.hgetall.return_value = {}
    redis.publish.return_value = None
    redis.close.return_value = None
    return redis


@pytest.fixture
def mock_storage():
    """Create a mock storage client."""
    storage = MagicMock()
    storage.upload_file = AsyncMock(return_value="r2://ceq-assets/outputs/test.png")
    storage.download_file = AsyncMock(return_value=b"test data")
    storage.delete_file = AsyncMock(return_value=True)
    return storage


@pytest.fixture
def mock_comfyui():
    """Create a mock ComfyUI executor."""
    comfyui = MagicMock()
    comfyui.execute = AsyncMock(return_value={
        "outputs": ["/tmp/output.png"],
        "execution_time": 5.2,
        "vram_peak": 12.5,
    })
    comfyui.is_ready = AsyncMock(return_value=True)
    comfyui.shutdown = AsyncMock()
    return comfyui


@pytest.fixture
def sample_job_data():
    """Sample job data for testing."""
    return {
        "id": "test-job-123",
        "workflow_id": "workflow-456",
        "input": {
            "workflow_json": {
                "nodes": [
                    {"id": "1", "type": "KSampler", "inputs": {}},
                ],
            },
            "params": {
                "prompt": "a test image",
                "seed": 12345,
            },
            "job_id": "test-job-123",
        },
    }


@pytest.fixture
def sample_workflow_json():
    """Sample ComfyUI workflow JSON."""
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": 8,
                "denoise": 1,
                "latent_image": ["5", 0],
                "model": ["4", 0],
                "negative": ["7", 0],
                "positive": ["6", 0],
                "sampler_name": "euler",
                "scheduler": "normal",
                "seed": 8566257,
                "steps": 20,
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"batch_size": 1, "height": 1024, "width": 1024},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": "beautiful landscape"},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": "ugly, blurry"},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "ComfyUI", "images": ["8", 0]},
        },
    }
