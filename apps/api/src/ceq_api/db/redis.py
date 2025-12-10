"""Redis connection management for job queue."""

from typing import Any

import redis.asyncio as redis

from ceq_api.config import get_settings

settings = get_settings()

# Global Redis client
_redis: redis.Redis | None = None


async def init_redis() -> None:
    """
    Initialize Redis connection.
    
    Called during application startup.
    """
    global _redis

    _redis = redis.from_url(
        str(settings.redis_url),
        decode_responses=True,
    )

    # Test connection
    await _redis.ping()
    print(f"   Redis connected: {settings.redis_url.host}:{settings.redis_url.port}")


async def close_redis() -> None:
    """
    Close Redis connection.
    
    Called during application shutdown.
    """
    global _redis

    if _redis is not None:
        await _redis.close()
        _redis = None
        print("   Redis connection closed")


def get_redis() -> redis.Redis:
    """
    Get the Redis client.
    
    Used as a FastAPI dependency:
    
        @router.post("/jobs")
        async def create_job(redis: Redis = Depends(get_redis)):
            ...
    """
    if _redis is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis


async def enqueue_job(job_data: dict[str, Any]) -> None:
    """
    Add a job to the processing queue.
    
    Jobs are stored as JSON in a Redis list.
    """
    import json

    if _redis is None:
        raise RuntimeError("Redis not initialized")

    await _redis.lpush("ceq:jobs:pending", json.dumps(job_data))


async def publish_job_update(job_id: str, update: dict[str, Any]) -> None:
    """
    Publish a job status update for WebSocket relay.
    """
    import json

    if _redis is None:
        raise RuntimeError("Redis not initialized")

    await _redis.publish(f"ceq:job:{job_id}:status", json.dumps(update))


async def get_job_status(job_id: str) -> dict[str, Any] | None:
    """
    Get current job status from Redis.
    """
    if _redis is None:
        raise RuntimeError("Redis not initialized")

    data = await _redis.hgetall(f"ceq:job:{job_id}")
    return dict(data) if data else None
