"""Job management and status endpoints."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth.janua import JanuaUser, get_current_user
from ceq_api.db.redis import get_redis, publish_job_update
from ceq_api.db.session import get_db
from ceq_api.models.job import Job, JobStatus as JobStatusEnum
from ceq_api.models.output import Output

router = APIRouter()


# === Pydantic Models ===


class OutputResponse(BaseModel):
    """Output file response."""

    id: UUID
    filename: str
    storage_uri: str
    file_type: str
    file_size_bytes: int
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    preview_url: str | None = None

    class Config:
        from_attributes = True


class JobStatusResponse(BaseModel):
    """Job status response model."""

    id: UUID
    workflow_id: UUID
    status: str = Field(description="queued | running | completed | failed | cancelled")
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    current_node: str | None = Field(default=None, description="Currently executing node")
    error: str | None = None
    input_params: dict[str, Any]
    outputs: list[OutputResponse] = Field(default_factory=list)
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    gpu_seconds: float = Field(default=0.0)
    cold_start_ms: int = Field(default=0)
    worker_id: str | None = None
    brand_message: str = Field(description="Brand-voice status message")

    class Config:
        from_attributes = True

    @classmethod
    def from_job(cls, job: Job) -> "JobStatusResponse":
        """Create response from Job model with brand message."""
        return cls(
            id=job.id,
            workflow_id=job.workflow_id,
            status=job.status,
            progress=job.progress,
            current_node=job.current_node,
            error=job.error,
            input_params=job.input_params,
            outputs=[OutputResponse.from_orm(o) for o in job.outputs] if hasattr(job, 'outputs') and job.outputs else [],
            queued_at=job.queued_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            gpu_seconds=job.gpu_seconds,
            cold_start_ms=job.cold_start_ms,
            worker_id=job.worker_id,
            brand_message=STATUS_MESSAGES.get(job.status, "Processing..."),
        )


class JobListResponse(BaseModel):
    """Paginated job list response."""

    jobs: list[JobStatusResponse]
    total: int
    skip: int
    limit: int


# === Brand Messages ===

STATUS_MESSAGES = {
    "queued": "In the crucible...",
    "running": "Transmuting latent space...",
    "completed": "Materialized. ✨",
    "failed": "Chaos won this round.",
    "cancelled": "Entropy released.",
}


# === Endpoints ===


@router.get("/", response_model=JobListResponse)
async def list_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status_filter: str | None = Query(None, description="Filter by status"),
    workflow_id: UUID | None = Query(None, description="Filter by workflow"),
) -> JobListResponse:
    """
    List jobs.

    View your transmutation queue.
    """
    # Build query
    conditions = [Job.user_id == user.id]

    if status_filter:
        if status_filter not in [s.value for s in JobStatusEnum]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {', '.join(s.value for s in JobStatusEnum)}",
            )
        conditions.append(Job.status == status_filter)

    if workflow_id:
        conditions.append(Job.workflow_id == workflow_id)

    # Count total
    count_query = select(Job).where(and_(*conditions))
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    # Fetch with pagination (outputs auto-loaded via lazy="selectin")
    query = (
        select(Job)
        .where(and_(*conditions))
        .order_by(Job.queued_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    jobs = result.scalars().all()

    return JobListResponse(
        jobs=[JobStatusResponse.from_job(job) for job in jobs],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> JobStatusResponse:
    """
    Get job status.

    Check on your transmutation progress.
    """
    # Outputs auto-loaded via lazy="selectin"
    query = select(Job).where(Job.id == job_id)
    result = await db.execute(query)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found in the crucible.",
        )

    # Authorization check
    if job.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This transmutation belongs to another alchemist.",
        )

    return JobStatusResponse.from_job(job)


@router.get("/{job_id}/poll", response_model=JobStatusResponse)
async def poll_job_status(
    job_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> JobStatusResponse:
    """
    Poll job status from Redis (faster than DB).

    For real-time updates, use the WebSocket endpoint.
    """
    redis = get_redis()

    # Try Redis first for speed
    redis_data = await redis.hgetall(f"ceq:job:{job_id}")

    if redis_data:
        # Update from Redis cache
        query = select(Job).where(Job.id == job_id)
        result = await db.execute(query)
        job = result.scalar_one_or_none()

        if job and job.user_id == user.id:
            # Merge Redis data (more current) with DB data
            if "status" in redis_data:
                job.status = redis_data["status"]
            if "progress" in redis_data:
                job.progress = float(redis_data["progress"])
            if "current_node" in redis_data:
                job.current_node = redis_data["current_node"]

            return JobStatusResponse.from_job(job)

    # Fall back to regular DB query
    return await get_job(job_id, db, user)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(
    job_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> None:
    """
    Cancel a job.

    Abort transmutation - entropy returns to chaos.
    """
    query = select(Job).where(Job.id == job_id)
    result = await db.execute(query)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found in the crucible.",
        )

    # Authorization check
    if job.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This transmutation belongs to another alchemist.",
        )

    # Check if cancellable
    if job.status not in [JobStatusEnum.QUEUED.value, JobStatusEnum.RUNNING.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job with status: {job.status}",
        )

    # Update job status
    job.status = JobStatusEnum.CANCELLED.value
    job.completed_at = datetime.utcnow()

    # Publish cancel signal to worker via Redis
    redis = get_redis()
    await redis.publish(f"ceq:job:{job_id}:control", json.dumps({"action": "cancel"}))

    # Remove from queue if still queued
    await redis.lrem("ceq:jobs:pending", 0, json.dumps({"job_id": str(job_id)}))

    # Publish status update for WebSocket listeners
    await publish_job_update(
        str(job_id),
        {
            "type": "cancelled",
            "data": {"message": "Entropy released."},
        },
    )


@router.websocket("/{job_id}/stream")
async def stream_job_progress(
    websocket: WebSocket,
    job_id: UUID,
) -> None:
    """
    Stream real-time job progress via WebSocket.

    Live feed from the transmutation chamber.

    Message format:
    {
        "type": "progress" | "node_start" | "node_complete" | "output" | "error" | "complete",
        "data": { ... }
    }
    """
    await websocket.accept()

    redis = get_redis()
    pubsub = redis.pubsub()

    try:
        # Subscribe to job status updates
        channel = f"ceq:job:{job_id}:status"
        await pubsub.subscribe(channel)

        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "data": {
                "job_id": str(job_id),
                "message": "Tuned into the transmutation frequency... 📡",
            },
        })

        # Get initial status from Redis
        initial_status = await redis.hgetall(f"ceq:job:{job_id}")
        if initial_status:
            await websocket.send_json({
                "type": "status",
                "data": {
                    "status": initial_status.get("status", "queued"),
                    "progress": float(initial_status.get("progress", 0)),
                    "current_node": initial_status.get("current_node"),
                    "message": STATUS_MESSAGES.get(
                        initial_status.get("status", "queued"),
                        "Processing...",
                    ),
                },
            })

        # Handle incoming messages and pubsub in parallel
        async def listen_pubsub():
            """Listen for Redis pubsub messages."""
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await websocket.send_json(data)

                        # Check for terminal states
                        if data.get("type") in ["complete", "error", "cancelled"]:
                            return
                    except json.JSONDecodeError:
                        pass

        async def handle_client_messages():
            """Handle incoming WebSocket messages from client."""
            while True:
                try:
                    data = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=30.0,
                    )
                    if data == "ping":
                        await websocket.send_json({"type": "pong"})
                except asyncio.TimeoutError:
                    # Send keepalive
                    await websocket.send_json({"type": "keepalive"})
                except WebSocketDisconnect:
                    raise

        # Run both tasks concurrently
        await asyncio.gather(
            listen_pubsub(),
            handle_client_messages(),
            return_exceptions=True,
        )

    except WebSocketDisconnect:
        # Client disconnected gracefully
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "data": {"message": str(e)},
            })
        except:
            pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        try:
            await websocket.close()
        except:
            pass


@router.get("/{job_id}/outputs", response_model=list[OutputResponse])
async def list_job_outputs(
    job_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> list[OutputResponse]:
    """
    List outputs from a completed job.

    Retrieve the materialized artifacts.
    """
    # First verify job access
    job_query = select(Job).where(Job.id == job_id)
    job_result = await db.execute(job_query)
    job = job_result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    if job.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )

    # Fetch outputs
    output_query = select(Output).where(Output.job_id == job_id)
    output_result = await db.execute(output_query)
    outputs = output_result.scalars().all()

    return [OutputResponse.from_orm(o) for o in outputs]
