"""Authenticated HTTPS job-lease API for external GPU workers.

``/v1/worker/*`` lets a GPU worker running **outside** the cluster (Vast.ai) pull
and complete jobs over authenticated HTTPS instead of connecting to Redis
directly. That removes the public-Redis requirement documented in
``docs/GPU_COMPUTE_STRATEGY.md`` — the queue stays cluster-internal and the only
thing on the public internet is this TLS API, gated on a Janua
``client_credentials`` token carrying the dedicated ``ceq:worker`` scope.

Lifecycle::

    POST /v1/worker/lease                  claim a job (visibility timeout starts)
    POST /v1/worker/jobs/{id}/heartbeat    extend the lease while work continues
    POST /v1/worker/jobs/{id}/complete     land results (same path as Redis mode)
    POST /v1/worker/jobs/{id}/fail         requeue, or dead-letter when spent

Completion deliberately reuses ``jobs.report_job_outputs`` — the exact function
the Redis worker's ``X-CEQ-Worker-Token`` callback already calls. Both modes
therefore persist outputs, refund credits, fire user webhooks and publish
WebSocket updates through one code path; there is no second, drifting
implementation of "what it means for a job to be done".

Artifacts: the worker uploads to R2 itself (``ceq_worker.storage``) and reports
``storage_uri`` descriptors here, identical to Redis mode. Artifact *bytes* never
traverse this API — a 40MB PNG through the API pod would be a needless hop when
the worker already holds R2 credentials. Workers without R2 credentials can call
``POST /v1/worker/jobs/{id}/upload-url`` to mint a presigned PUT and then report
the resulting URI, so the bytes still go straight to R2.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api import worker_lease
from ceq_api.auth.janua import JanuaUser, get_worker_principal
from ceq_api.config import get_settings
from ceq_api.db.redis import get_redis
from ceq_api.db.session import get_db
from ceq_api.models.job import Job
from ceq_api.models.job import JobStatus as JobStatusEnum
from ceq_api.routers.jobs import (
    JobCompletionReport,
    JobOutputReport,
    persist_job_completion,
)
from ceq_api.storage import get_storage
from ceq_api.worker_lease import LeaseOutcome

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


# === Request / response models ===============================================


class LeaseRequest(BaseModel):
    """Worker's request for the next available job."""

    worker_id: str = Field(
        min_length=1,
        max_length=128,
        description="Stable identity of this worker process (e.g. vast instance id).",
    )
    ttl_seconds: int | None = Field(
        default=None,
        ge=10,
        le=3600,
        description=(
            "Requested visibility timeout. Clamped to the server ceiling; "
            "omit to use the server default."
        ),
    )


class LeasedJobResponse(BaseModel):
    """A claimed job plus its lease terms."""

    job_id: UUID
    payload: dict[str, Any] = Field(
        description="The job envelope, byte-identical to what Redis-mode workers pop."
    )
    attempt: int = Field(description="1 on first delivery; higher after a requeue.")
    lease_expires_at: datetime
    heartbeat_interval_seconds: int = Field(
        description="Heartbeat at least this often to keep the lease alive."
    )


class HeartbeatRequest(BaseModel):
    """Lease extension, optionally carrying progress for live status."""

    worker_id: str = Field(min_length=1, max_length=128)
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    current_node: str | None = Field(default=None, max_length=255)


class HeartbeatResponse(BaseModel):
    """New lease deadline after a successful extension."""

    job_id: UUID
    lease_expires_at: datetime
    cancel_requested: bool = Field(
        description=(
            "True when the job was cancelled while running. The worker should "
            "abandon the work and call /fail with cancelled=true."
        )
    )


class CompleteRequest(BaseModel):
    """Terminal success report from a worker."""

    worker_id: str = Field(min_length=1, max_length=128)
    outputs: list[JobOutputReport] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    gpu_seconds: float | None = Field(default=None, ge=0.0)
    cold_start_ms: int | None = Field(default=None, ge=0)


class FailRequest(BaseModel):
    """Terminal or retryable failure report from a worker."""

    worker_id: str = Field(min_length=1, max_length=128)
    error: str = Field(min_length=1, max_length=4000)
    retryable: bool = Field(
        default=True,
        description=(
            "When true the job returns to the queue if attempts remain. Set "
            "false for errors a retry cannot fix (bad workflow, missing model)."
        ),
    )
    cancelled: bool = Field(
        default=False,
        description="The job was cancelled mid-flight rather than failing.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    gpu_seconds: float | None = Field(default=None, ge=0.0)


class WorkerJobResultResponse(BaseModel):
    """Outcome of a terminal worker report."""

    job_id: UUID
    status: str
    outputs_persisted: int
    requeued: bool = False
    dead_lettered: bool = False
    attempt: int = 0


class UploadUrlRequest(BaseModel):
    """Request a presigned R2 PUT for one artifact."""

    worker_id: str = Field(min_length=1, max_length=128)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="application/octet-stream", max_length=255)


class UploadUrlResponse(BaseModel):
    """Presigned destination for a worker artifact."""

    upload_url: str
    storage_uri: str
    expires_in_seconds: int


# === Helpers =================================================================


def _heartbeat_interval(ttl_seconds: int) -> int:
    """Advise a heartbeat cadence with room for one missed beat.

    A third of the TTL means a worker can lose one heartbeat entirely (transient
    network blip on a Vast box) and still renew before the reaper takes the job.
    """
    return max(5, ttl_seconds // 3)


def _lease_ttl(requested: int | None) -> int:
    """Clamp a worker's requested TTL to the server-configured ceiling."""
    default = settings.worker_lease_ttl_seconds
    if requested is None:
        return default
    return min(requested, default)


async def _require_lease(redis: Any, job_id: UUID, worker_id: str) -> dict[str, str]:
    """Load the lease for ``job_id`` and assert this worker still owns it.

    A worker whose lease expired and was re-claimed elsewhere gets 409 rather
    than being allowed to write a result for a job someone else now owns. That
    is the guard that makes at-least-once delivery safe: the *current* owner's
    write is the one that lands.
    """
    lease = await worker_lease.get_lease(redis, str(job_id))
    if lease is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No open lease for this job. It expired and was requeued, or it "
                "was already completed. Abandon this work unit."
            ),
        )
    if lease.get("worker_id") != worker_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This job is leased to a different worker. Your lease expired "
                "and the job was re-claimed. Abandon this work unit."
            ),
        )
    return lease


def _lease_attempts(lease: dict[str, str]) -> int:
    """Parse the attempt counter out of a lease record."""
    try:
        return int(lease.get("attempts", "1"))
    except ValueError:
        return 1


# === Endpoints ===============================================================


@router.post("/lease", response_model=LeasedJobResponse | None)
async def lease_next_job(
    data: LeaseRequest,
    principal: Annotated[JanuaUser, Depends(get_worker_principal)],
) -> LeasedJobResponse | None:
    """Claim the next pending job, opening a visibility-timeout lease.

    Returns ``204 No Content`` when the queue is empty — workers long-poll this
    endpoint, and an empty queue is the normal case, not an error.

    The claim is a single Lua ``RPOPLPUSH pending -> processing`` plus a lease
    write, so it is atomic against other HTTPS leasers *and* against legacy
    in-cluster Redis workers doing ``BRPOPLPUSH`` on the same lists. Exactly one
    claimant can win any payload.
    """
    redis = get_redis()
    ttl = _lease_ttl(data.ttl_seconds)

    # Recover crashed workers' jobs before claiming: a worker asking for work is
    # precisely when an abandoned job should become claimable again.
    try:
        reaped = await worker_lease.reap_expired(
            redis, max_attempts=settings.worker_lease_max_attempts
        )
        if reaped:
            logger.info("Lease reaper recovered %s job(s): %s", len(reaped), reaped)
    except Exception:  # noqa: BLE001 - reaping must never block a lease request
        logger.exception("Lease reaper failed; continuing to claim")

    leased = await worker_lease.claim_next_job(
        redis,
        worker_id=data.worker_id,
        client_id=principal.client_id or "",
        ttl_seconds=ttl,
    )

    if leased is None:
        raise HTTPException(status_code=status.HTTP_204_NO_CONTENT)

    try:
        job_uuid = UUID(leased.job_id)
    except ValueError:
        # A non-UUID job id cannot map to a Job row. Retire it rather than
        # handing a worker something it can never report on.
        logger.error("Leased job carried non-UUID id %r; dead-lettering", leased.job_id)
        await worker_lease.dead_letter_lease(
            redis,
            job_id=leased.job_id,
            worker_id=data.worker_id,
            reason="non-uuid job id",
        )
        raise HTTPException(status_code=status.HTTP_204_NO_CONTENT) from None

    logger.info(
        "Job %s leased to worker %s (client=%s, attempt=%s, ttl=%ss)",
        job_uuid,
        data.worker_id,
        principal.client_id,
        leased.attempts,
        ttl,
    )

    return LeasedJobResponse(
        job_id=job_uuid,
        payload=leased.payload,
        attempt=leased.attempts,
        lease_expires_at=datetime.fromtimestamp(leased.expires_at, tz=UTC),
        heartbeat_interval_seconds=_heartbeat_interval(ttl),
    )


@router.post("/jobs/{job_id}/heartbeat", response_model=HeartbeatResponse)
async def heartbeat_job(
    job_id: UUID,
    data: HeartbeatRequest,
    principal: Annotated[JanuaUser, Depends(get_worker_principal)],
) -> HeartbeatResponse:
    """Extend this worker's lease and publish live progress.

    Also surfaces ``cancel_requested``: cancellation is signalled through the
    same Redis job hash the in-cluster worker watches, so an external worker
    learns about a user's cancel on its next heartbeat without needing a Redis
    subscription.
    """
    redis = get_redis()
    await _require_lease(redis, job_id, data.worker_id)

    outcome, expires_at = await worker_lease.heartbeat_lease(
        redis,
        job_id=str(job_id),
        worker_id=data.worker_id,
        ttl_seconds=settings.worker_lease_ttl_seconds,
        max_seconds=settings.worker_lease_max_seconds,
    )

    if outcome == LeaseOutcome.NOT_OWNER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This job is leased to a different worker. Abandon this work unit.",
        )
    if outcome != LeaseOutcome.OK or expires_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Lease could not be extended — it expired or hit the maximum "
                "lease duration. Abandon this work unit."
            ),
        )

    # Mirror progress into the Redis job hash so /v1/jobs/{id}/poll and the
    # WebSocket relay see external workers exactly as they see in-cluster ones.
    cancel_requested = False
    try:
        job_state = await redis.hgetall(f"ceq:job:{job_id}")
        job_state = dict(job_state) if job_state else {}
        cancel_requested = (
            job_state.get("status") == JobStatusEnum.CANCELLED.value
            or str(job_state.get("cancel_requested", "")).lower() == "true"
        )

        mapping: dict[str, str] = {
            "status": JobStatusEnum.RUNNING.value,
            "worker_id": data.worker_id,
        }
        if data.progress is not None:
            mapping["progress"] = str(data.progress)
        if data.current_node is not None:
            mapping["current_node"] = data.current_node
        if not cancel_requested:
            await redis.hset(f"ceq:job:{job_id}", mapping=mapping)
    except Exception as exc:  # noqa: BLE001 - status mirroring is best effort
        logger.debug("Unable to mirror heartbeat state for job %s: %s", job_id, exc)

    return HeartbeatResponse(
        job_id=job_id,
        lease_expires_at=datetime.fromtimestamp(expires_at, tz=UTC),
        cancel_requested=cancel_requested,
    )


@router.post("/jobs/{job_id}/complete", response_model=WorkerJobResultResponse)
async def complete_job(
    job_id: UUID,
    data: CompleteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[JanuaUser, Depends(get_worker_principal)],
) -> WorkerJobResultResponse:
    """Land a successful result and close the lease.

    Persistence goes through the same ``persist_job_completion`` the Redis
    worker's callback uses, so outputs, credit handling, user webhooks and
    WebSocket updates behave identically in both modes.

    Ordering: persist FIRST, release the lease SECOND. If the process dies
    between the two, the lease expires and the job is re-run — which is safe
    (outputs upsert on ``(job_id, storage_uri)``). Releasing first would risk
    losing a result entirely, which is not.
    """
    redis = get_redis()
    lease = await _require_lease(redis, job_id, data.worker_id)

    report = JobCompletionReport(
        status=JobStatusEnum.COMPLETED.value,
        progress=1.0,
        error=None,
        outputs=data.outputs,
        metadata={
            **data.metadata,
            "lease_mode": True,
            "lease_client_id": principal.client_id,
            "lease_attempt": _lease_attempts(lease),
        },
        worker_id=data.worker_id,
        gpu_seconds=data.gpu_seconds,
        cold_start_ms=data.cold_start_ms,
    )

    result = await persist_job_completion(job_id, report, db)

    await worker_lease.release_lease(
        redis, job_id=str(job_id), worker_id=data.worker_id
    )

    logger.info(
        "Job %s completed by worker %s (%s outputs)",
        job_id,
        data.worker_id,
        result.outputs_persisted,
    )

    return WorkerJobResultResponse(
        job_id=job_id,
        status=result.status,
        outputs_persisted=result.outputs_persisted,
        attempt=_lease_attempts(lease),
    )


@router.post("/jobs/{job_id}/fail", response_model=WorkerJobResultResponse)
async def fail_job(
    job_id: UUID,
    data: FailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[JanuaUser, Depends(get_worker_principal)],
) -> WorkerJobResultResponse:
    """Report a failure: requeue if attempts remain, else retire the job.

    Retry semantics match what Redis mode already does implicitly — its
    ``_process_job`` except-branch LPUSHes the payload back to ``pending`` — but
    with an explicit, bounded attempt counter instead of an unbounded loop. Past
    ``worker_lease_max_attempts`` (or on a non-retryable error) the job is marked
    ``failed`` in Postgres, credits are refunded by the shared completion path,
    and the payload is archived to ``ceq:jobs:lease:dead``.
    """
    redis = get_redis()
    lease = await _require_lease(redis, job_id, data.worker_id)
    attempts = _lease_attempts(lease)

    retry_allowed = (
        data.retryable
        and not data.cancelled
        and attempts < settings.worker_lease_max_attempts
    )

    if retry_allowed:
        # Transient failure with budget left: hand the job back to the queue and
        # leave the Job row `running` — a retry is not a user-visible failure.
        outcome = await worker_lease.requeue_lease(
            redis,
            job_id=str(job_id),
            worker_id=data.worker_id,
            attempts=attempts,
        )
        if outcome != LeaseOutcome.OK:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lease no longer held; job was already recovered.",
            )

        logger.warning(
            "Job %s requeued after attempt %s of %s (worker=%s): %s",
            job_id,
            attempts,
            settings.worker_lease_max_attempts,
            data.worker_id,
            data.error,
        )
        return WorkerJobResultResponse(
            job_id=job_id,
            status=JobStatusEnum.QUEUED.value,
            outputs_persisted=0,
            requeued=True,
            attempt=attempts,
        )

    terminal_status = (
        JobStatusEnum.CANCELLED.value if data.cancelled else JobStatusEnum.FAILED.value
    )
    report = JobCompletionReport(
        status=terminal_status,
        progress=0.0,
        error=data.error,
        outputs=[],
        metadata={
            **data.metadata,
            "lease_mode": True,
            "lease_client_id": principal.client_id,
            "lease_attempts": attempts,
            "lease_retryable": data.retryable,
        },
        worker_id=data.worker_id,
        gpu_seconds=data.gpu_seconds,
    )

    result = await persist_job_completion(job_id, report, db)

    await worker_lease.dead_letter_lease(
        redis,
        job_id=str(job_id),
        worker_id=data.worker_id,
        reason=data.error[:500],
    )

    logger.error(
        "Job %s retired as %s after %s attempt(s) (worker=%s): %s",
        job_id,
        terminal_status,
        attempts,
        data.worker_id,
        data.error,
    )

    return WorkerJobResultResponse(
        job_id=job_id,
        status=result.status,
        outputs_persisted=result.outputs_persisted,
        dead_lettered=True,
        attempt=attempts,
    )


@router.post("/jobs/{job_id}/upload-url", response_model=UploadUrlResponse)
async def create_artifact_upload_url(
    job_id: UUID,
    data: UploadUrlRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[JanuaUser, Depends(get_worker_principal)],
) -> UploadUrlResponse:
    """Mint a presigned R2 PUT for one artifact of a leased job.

    For workers that do not carry R2 credentials of their own. The bytes still
    go worker -> R2 directly; only the *authorization* to write one specific key
    passes through this API. The worker then reports the returned
    ``storage_uri`` in its ``/complete`` payload exactly as an R2-credentialed
    worker would.
    """
    redis = get_redis()
    await _require_lease(redis, job_id, data.worker_id)

    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    storage = await get_storage()
    if not getattr(storage, "is_configured", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Object storage is not configured on this deployment.",
        )

    # Key under the job so an artifact can never be written outside its own job
    # prefix, whatever filename the worker asks for.
    safe_name = data.filename.replace("/", "_").replace("\\", "_")
    key = f"outputs/{job_id}/{safe_name}"

    presigned = await storage.generate_upload_url(
        key=key,
        content_type=data.content_type,
        expires_in=settings.presigned_url_expiry_seconds,
    )

    return UploadUrlResponse(
        upload_url=presigned["upload_url"],
        storage_uri=presigned["storage_uri"],
        expires_in_seconds=settings.presigned_url_expiry_seconds,
    )
