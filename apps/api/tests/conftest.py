"""Pytest fixtures for CEQ API tests."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from ceq_api.models import Base
from ceq_api.auth.janua import JanuaUser


# Test database URL (in-memory SQLite for tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Create async engine for tests."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session for tests."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
def mock_user() -> JanuaUser:
    """Create a mock authenticated user."""
    return JanuaUser(
        id=uuid4(),
        email="test@madfam.io",
        name="Test User",
        org_id=uuid4(),
        roles=["user"],
    )


@pytest.fixture
def mock_admin_user() -> JanuaUser:
    """Create a mock admin user."""
    return JanuaUser(
        id=uuid4(),
        email="admin@madfam.io",
        name="Admin User",
        org_id=uuid4(),
        roles=["admin", "user"],
    )


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.hgetall.return_value = {}
    redis.hset.return_value = None
    redis.lpush.return_value = None
    redis.lrem.return_value = None
    redis.publish.return_value = None
    redis.close.return_value = None
    return redis


@pytest.fixture
def mock_storage():
    """Create a mock storage client."""
    storage = MagicMock()
    storage.is_configured = True
    storage.get_public_url.return_value = "https://r2.example.com/test"
    storage.generate_upload_url = AsyncMock(return_value={
        "upload_url": "https://r2.example.com/presigned",
        "storage_uri": "r2://ceq-assets/test/file.png",
    })
    storage.generate_download_url = AsyncMock(return_value="https://r2.example.com/download")
    storage.delete_object = AsyncMock(return_value=True)
    return storage


@pytest.fixture
def app(db_session, mock_user, mock_redis, mock_storage) -> FastAPI:
    """Create test FastAPI application with mocked dependencies."""
    from ceq_api.main import app as main_app
    from ceq_api.db import get_db
    from ceq_api.auth import get_current_user
    from ceq_api.db.redis import get_redis
    from ceq_api.storage import get_storage

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return mock_user

    def override_get_redis():
        return mock_redis

    async def override_get_storage():
        return mock_storage

    main_app.dependency_overrides[get_db] = override_get_db
    main_app.dependency_overrides[get_current_user] = override_get_current_user
    main_app.dependency_overrides[get_redis] = override_get_redis
    main_app.dependency_overrides[get_storage] = override_get_storage

    yield main_app

    main_app.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create synchronous test client."""
    return TestClient(app)


@pytest_asyncio.fixture
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


# Sample data fixtures

@pytest.fixture
def sample_workflow_json() -> dict[str, Any]:
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
    }


@pytest.fixture
def sample_input_schema() -> dict[str, Any]:
    """Sample JSON Schema for workflow inputs."""
    return {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Text prompt for generation",
            },
            "seed": {
                "type": "integer",
                "description": "Random seed",
                "default": -1,
            },
        },
        "required": ["prompt"],
    }


@pytest.fixture
def sample_template_data(sample_workflow_json, sample_input_schema) -> dict[str, Any]:
    """Sample template data."""
    return {
        "name": "Test Template",
        "description": "A test template for unit tests",
        "category": "utility",
        "workflow_json": sample_workflow_json,
        "input_schema": sample_input_schema,
        "tags": ["test", "utility"],
        "model_requirements": ["sd_xl_base_1.0.safetensors"],
        "vram_requirement_gb": 12,
    }


@pytest.fixture
def sample_workflow_data(sample_workflow_json, sample_input_schema) -> dict[str, Any]:
    """Sample workflow data."""
    return {
        "name": "Test Workflow",
        "description": "A test workflow",
        "workflow_json": sample_workflow_json,
        "input_schema": sample_input_schema,
        "tags": ["test"],
        "is_public": False,
    }
