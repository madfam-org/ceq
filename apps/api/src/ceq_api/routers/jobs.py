"""Job management and status endpoints."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth.janua import JanuaUser, get_current_user, validate_token
from ceq_api.config import get_settings
from ceq_api.db.redis import get_redis, publish_job_update
from ceq_api.db.session import get_db
from ceq_api.logging import audit_logger
from ceq_api.metrics import record_job_cancellation, record_worker_completion_report
from ceq_api.models.job import Job
from ceq_api.models.job import JobStatus as JobStatusEnum
from ceq_api.models.output import Output
from ceq_api.services.job_webhooks import deliver_job_webhook
from ceq_api.storage import get_storage

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


# === Pydantic Models ===


class OutputResponse(BaseModel):
    """Output file response."""

    id: UUID
    filename: str
    storage_uri: str
    public_url: str | None = None
    file_type: str
    file_size_bytes: int
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    preview_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    published_to: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def from_output(
        cls,
        output: Output,
        public_url: str | None = None,
    ) -> OutputResponse:
        """Build job-context output response from an ORM output model."""
        return cls(
            id=output.id,
            filename=output.filename,
            storage_uri=output.storage_uri,
            public_url=public_url or output.storage_uri,
            file_type=output.file_type,
            file_size_bytes=output.file_size_bytes,
            width=output.width,
            height=output.height,
            duration_seconds=output.duration_seconds,
            preview_url=output.preview_url,
            metadata=output.output_metadata or {},
            published_to=output.published_to or [],
        )

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
    output_metadata: dict[str, Any] = Field(default_factory=dict)
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
    def from_job(cls, job: Job) -> JobStatusResponse:
        """Create response from Job model with brand message."""
        return cls(
            id=job.id,
            workflow_id=job.workflow_id,
            status=job.status,
            progress=job.progress,
            current_node=job.current_node,
            error=job.error,
            input_params=job.input_params,
            outputs=[
                OutputResponse.from_output(output)
                for output in job.outputs
            ]
            if hasattr(job, "outputs") and job.outputs
            else [],
            output_metadata=job.output_metadata or {},
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


class JobOutputReport(BaseModel):
    """Single output reported by a worker after execution."""

    filename: str = Field(min_length=1, max_length=255)
    storage_uri: str = Field(min_length=1, max_length=2048)
    file_type: str = Field(min_length=1, max_length=100)
    file_size_bytes: int = Field(ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    duration_seconds: float | None = Field(default=None, ge=0)
    preview_url: str | None = Field(default=None, max_length=2048)
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobCompletionReport(BaseModel):
    """Worker completion payload for durable job/output persistence."""

    status: str = Field(description="running | completed | failed | cancelled")
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    current_node: str | None = None
    error: str | None = None
    outputs: list[JobOutputReport] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    worker_id: str | None = None
    gpu_seconds: float | None = Field(default=None, ge=0.0)
    cold_start_ms: int | None = Field(default=None, ge=0)


class JobCompletionReportResponse(BaseModel):
    """Response after accepting a worker completion report."""

    job_id: UUID
    status: str
    outputs_persisted: int


# === Brand Messages ===

STATUS_MESSAGES = {
    "queued": "In the crucible...",
    "running": "Transmuting latent space...",
    "completed": "Materialized. ✨",
    "failed": "Chaos won this round.",
    "cancelled": "Entropy released.",
}


def _validate_worker_callback_token(token: str | None) -> None:
    """Reject worker callbacks unless the shared token matches."""
    expected = settings.job_completion_callback_token
    if not expected or token is None or not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid worker callback token.",
        )


async def _remove_pending_job(redis: Any, job_id: UUID) -> int:
    """Remove queued job payloads by matching both current and legacy shapes."""
    job_id_str = str(job_id)
    removed = 0

    for payload in (
        json.dumps({"id": job_id_str}),
        json.dumps({"job_id": job_id_str}),
    ):
        removed += int(await redis.lrem("ceq:jobs:pending", 0, payload) or 0)

    try:
        queue_items = await redis.lrange("ceq:jobs:pending", 0, -1)
    except Exception as exc:  # noqa: BLE001 - Redis mocks/clients differ by context
        logger.debug("Unable to scan pending queue for cancellation: %s", exc)
        return removed

    if not isinstance(queue_items, (list, tuple)):
        return removed

    for raw_payload in queue_items:
        try:
            payload = json.loads(raw_payload)
        except (TypeError, json.JSONDecodeError):
            continue

        input_payload = payload.get("input") if isinstance(payload, dict) else None
        input_payload = input_payload if isinstance(input_payload, dict) else {}
        candidate = (
            payload.get("id")
            or payload.get("job_id")
            or input_payload.get("job_id")
        )
        if candidate == job_id_str:
            removed += int(await redis.lrem("ceq:jobs:pending", 0, raw_payload) or 0)

    return removed


# === Endpoints ===


@router.get("/", response_model=JobListResponse)
async def list_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status_filter: str | None = Query(None, description="Filter by status"),
    workflow_id: UUID | None = Query(None, description="Filter by workflow"),  # noqa: B008
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
    count_query = select(func.count()).select_from(Job).where(and_(*conditions))
    count_result = await db.execute(count_query)
    total = count_result.scalar_one() or 0

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


@router.post("/{job_id}/outputs/report", response_model=JobCompletionReportResponse)
async def report_job_outputs(
    job_id: UUID,
    data: JobCompletionReport,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_ceq_worker_token: Annotated[
        str | None,
        Header(alias="X-CEQ-Worker-Token"),
    ] = None,
) -> JobCompletionReportResponse:
    """
    Persist a worker completion report.

    This endpoint is internal to CEQ workers. It makes job completion durable in
    PostgreSQL while Redis remains the real-time status transport.
    """
    _validate_worker_callback_token(x_ceq_worker_token)

    allowed_statuses = {status_value.value for status_value in JobStatusEnum}
    if data.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(allowed_statuses))}",
        )

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    if job.status == JobStatusEnum.CANCELLED.value and data.status != JobStatusEnum.CANCELLED.value:
        job.output_metadata = {
            **(job.output_metadata or {}),
            "ignored_worker_report_after_cancel": {
                "status": data.status,
                "reported_at": datetime.now(UTC).isoformat(),
                "worker_id": data.worker_id,
            },
        }
        await db.flush()
        record_worker_completion_report(job.status, 0)
        return JobCompletionReportResponse(
            job_id=job.id,
            status=job.status,
            outputs_persisted=0,
        )

    now = datetime.now(UTC)
    job.status = data.status
    if data.progress is not None:
        job.progress = data.progress
    elif data.status == JobStatusEnum.COMPLETED.value:
        job.progress = 1.0
    job.current_node = data.current_node
    job.error = data.error
    if data.worker_id:
        job.worker_id = data.worker_id
    if data.gpu_seconds is not None:
        job.gpu_seconds = data.gpu_seconds
    if data.cold_start_ms is not None:
        job.cold_start_ms = data.cold_start_ms
    if job.started_at is None and data.status in {
        JobStatusEnum.RUNNING.value,
        JobStatusEnum.COMPLETED.value,
        JobStatusEnum.FAILED.value,
    }:
        job.started_at = now
    if data.status in {
        JobStatusEnum.COMPLETED.value,
        JobStatusEnum.FAILED.value,
        JobStatusEnum.CANCELLED.value,
    }:
        job.completed_at = now

    job.output_metadata = {
        **(job.output_metadata or {}),
        **data.metadata,
        "worker_callback_reported_at": now.isoformat(),
    }

    outputs_persisted = 0
    persisted_outputs: list[Output] = []
    for output_report in data.outputs:
        existing_result = await db.execute(
            select(Output).where(
                Output.job_id == job.id,
                Output.storage_uri == output_report.storage_uri,
            )
        )
        output = existing_result.scalar_one_or_none()

        output_values = {
            "user_id": job.user_id,
            "filename": output_report.filename,
            "storage_uri": output_report.storage_uri,
            "file_type": output_report.file_type,
            "file_size_bytes": output_report.file_size_bytes,
            "width": output_report.width,
            "height": output_report.height,
            "duration_seconds": output_report.duration_seconds,
            "preview_url": output_report.preview_url,
            "output_metadata": output_report.metadata,
        }

        if output is None:
            output = Output(
                job_id=job.id,
                published_to=[],
                **output_values,
            )
            db.add(output)
        else:
            for key, value in output_values.items():
                setattr(output, key, value)

        persisted_outputs.append(output)
        outputs_persisted += 1

    await db.flush()
    record_worker_completion_report(job.status, outputs_persisted)

    if job.status in {
        JobStatusEnum.COMPLETED.value,
        JobStatusEnum.FAILED.value,
        JobStatusEnum.CANCELLED.value,
    }:
        try:
            storage = await get_storage()
            await deliver_job_webhook(job, persisted_outputs, storage)
        except Exception:  # noqa: BLE001 - completion persistence is source of truth
            logger.exception("Unexpected job webhook delivery failure for job %s", job_id)

    try:
        redis = get_redis()
        await redis.hset(
            f"ceq:job:{job_id}",
            mapping={
                "status": job.status,
                "progress": str(job.progress),
                "worker_id": job.worker_id or "",
            },
        )
        await publish_job_update(
            str(job_id),
            {
                "type": "complete" if job.status == JobStatusEnum.COMPLETED.value else job.status,
                "data": {
                    "status": job.status,
                    "progress": job.progress,
                    "outputs": outputs_persisted,
                    "message": STATUS_MESSAGES.get(job.status, "Processing..."),
                },
            },
        )
    except Exception as exc:  # noqa: BLE001 - DB persistence is the source of truth
        logger.debug("Unable to publish completion report to Redis: %s", exc)

    return JobCompletionReportResponse(
        job_id=job.id,
        status=job.status,
        outputs_persisted=outputs_persisted,
    )


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
    prior_status = job.status
    cancelled_at = datetime.now(UTC)
    job.status = JobStatusEnum.CANCELLED.value
    if prior_status == JobStatusEnum.QUEUED.value:
        job.progress = 0.0
        job.completed_at = cancelled_at
    else:
        job.progress = max(job.progress, 0.0)
    job.output_metadata = {
        **(job.output_metadata or {}),
        "cancel_requested_at": cancelled_at.isoformat(),
        "cancel_requested_from_status": prior_status,
    }

    # Audit log the cancellation
    audit_logger.log_job_operation(
        operation="cancel",
        job_id=str(job_id),
        user_id=str(user.id),
        workflow_id=str(job.workflow_id),
    )

    # Publish cancel signal to worker via Redis
    redis = get_redis()
    await redis.hset(
        f"ceq:job:{job_id}",
        mapping={
            "status": JobStatusEnum.CANCELLED.value,
            "progress": str(job.progress),
            "cancel_requested": "true",
        },
    )
    await redis.publish(
        f"ceq:job:{job_id}:control",
        json.dumps({
            "action": "cancel",
            "job_id": str(job_id),
            "requested_at": cancelled_at.isoformat(),
        }),
    )

    # Remove from queue if still queued.
    await _remove_pending_job(redis, job_id)
    record_job_cancellation()

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
    token: str | None = None,
) -> None:
    """
    Stream real-time job progress via WebSocket.

    Live feed from the transmutation chamber.

    Authentication: Pass token as query parameter: ?token=<jwt>

    Message format:
    {
        "type": "progress" | "node_start" | "node_complete" | "output" | "error" | "complete",
        "data": { ... }
    }
    """
    # Validate authentication before accepting connection
    user = None
    if token:
        user = await validate_token(token)

    if not user:
        # Reject unauthenticated connections
        await websocket.close(code=4001, reason="Authentication required")
        logger.warning(f"WebSocket connection rejected for job {job_id}: no valid token")
        return

    # Verify user owns this job (requires DB check)
    from ceq_api.db.session import async_session_maker

    async with async_session_maker() as db:
        query = select(Job).where(Job.id == job_id)
        result = await db.execute(query)
        job = result.scalar_one_or_none()

        if not job:
            await websocket.close(code=4004, reason="Job not found")
            return

        if job.user_id != user.id:
            await websocket.close(code=4003, reason="Access denied")
            logger.warning(f"WebSocket access denied for job {job_id}: user {user.id} is not owner")
            return

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
                    except json.JSONDecodeError as e:
                        logger.debug(f"Malformed JSON in pubsub message: {e}")

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
                except TimeoutError:
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
        logger.debug(f"WebSocket client disconnected from job {job_id}")
    except Exception as e:
        logger.warning(f"WebSocket error for job {job_id}: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "data": {"message": str(e)},
            })
        except Exception as send_err:
            logger.debug(f"Failed to send error to WebSocket: {send_err}")
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        try:
            await websocket.close()
        except Exception as close_err:
            logger.debug(f"Failed to close WebSocket: {close_err}")


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
    storage = await get_storage()

    return [
        OutputResponse(
            id=output.id,
            filename=output.filename,
            storage_uri=output.storage_uri,
            public_url=storage.get_public_url(output.storage_uri),
            file_type=output.file_type,
            file_size_bytes=output.file_size_bytes,
            width=output.width,
            height=output.height,
            duration_seconds=output.duration_seconds,
            preview_url=output.preview_url,
            metadata=output.output_metadata or {},
            published_to=output.published_to or [],
        )
        for output in outputs
    ]
