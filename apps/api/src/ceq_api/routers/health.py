"""Health check endpoints."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.config import get_settings
from ceq_api.db import get_db
from ceq_api.db.redis import get_redis
from ceq_api.resilience import CircuitBreaker

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    version: str


class ReadinessResponse(BaseModel):
    """Readiness check response with dependency status."""

    status: str
    message: str
    database: str
    redis: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.

    Returns basic service health without checking dependencies.
    Use /ready for full readiness check.
    """
    return HealthResponse(
        status="healthy",
        service="ceq-api",
        version=settings.app_version,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReadinessResponse:
    """
    Readiness check - validates all dependencies.

    Checks database and Redis connectivity.
    Returns "ready" only if all dependencies are available.
    """
    db_status = "ok"
    redis_status = "ok"
    all_healthy = True

    # Check database connection
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "error"
        all_healthy = False

    # Check Redis connection
    try:
        redis_client = get_redis()
        await redis_client.ping()
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        redis_status = "error"
        all_healthy = False

    if all_healthy:
        return ReadinessResponse(
            status="ready",
            message="Entropy containment stable. All systems operational.",
            database=db_status,
            redis=redis_status,
        )
    else:
        return ReadinessResponse(
            status="degraded",
            message="Entropy fluctuations detected. Some systems impaired.",
            database=db_status,
            redis=redis_status,
        )


@router.get("/circuits")
async def circuit_breaker_status() -> dict[str, Any]:
    """
    Get status of all circuit breakers.

    Returns current state and statistics for monitoring.
    """
    stats = CircuitBreaker.get_all_stats()

    # Calculate overall health
    open_circuits = [
        name for name, s in stats.items()
        if s["state"] == "open"
    ]

    return {
        "status": "healthy" if not open_circuits else "degraded",
        "open_circuits": open_circuits,
        "circuits": stats,
    }
