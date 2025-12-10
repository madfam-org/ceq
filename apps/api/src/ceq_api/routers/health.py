"""Health check endpoints."""

from fastapi import APIRouter

from ceq_api.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "ceq-api",
        "version": settings.app_version,
    }


@router.get("/ready")
async def readiness_check() -> dict[str, str]:
    """Readiness check - validates dependencies."""
    # TODO: Check database connection
    # TODO: Check Redis connection
    # TODO: Check Furnace availability
    return {
        "status": "ready",
        "message": "Entropy containment stable.",
    }
