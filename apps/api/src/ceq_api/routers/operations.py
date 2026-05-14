"""Admin operations endpoints for production acceptance and recovery."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth.janua import JanuaUser, require_admin
from ceq_api.config import get_settings
from ceq_api.db.redis import get_redis
from ceq_api.db.session import get_db
from ceq_api.metrics import record_completion_dead_letter_replay

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


class OperationsStatusResponse(BaseModel):
    """Production-facing runtime status for operator acceptance gates."""

    environment: str
    app_version: str
    r2_configured: bool
    janua_enabled: bool
    callback_token_configured: bool
    webhook_secret_configured: bool
    alembic_revision: str | None = None
    redis: dict[str, int | None | bool] = Field(default_factory=dict)


class CompletionDeadLetterEntry(BaseModel):
    """One exhausted worker completion callback payload."""

    index: int
    job_id: str | None = None
    worker_id: str | None = None
    url: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    status_code: int | None = None
    attempts: int | None = None
    malformed: bool = False


class CompletionDeadLetterListResponse(BaseModel):
    """Paged Redis dead-letter list response."""

    redis_key: str
    count: int | None
    items: list[CompletionDeadLetterEntry]


class CompletionDeadLetterReplayResponse(BaseModel):
    """Replay result for one dead-lettered callback."""

    index: int
    job_id: str | None
    status: str
    upstream_status_code: int
    removed: bool


class CompletionDeadLetterDiscardResponse(BaseModel):
    """Discard result for one dead-lettered callback."""

    index: int
    removed: bool


def _raw_to_text(raw: Any) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def _parse_dead_letter(raw: Any, index: int) -> CompletionDeadLetterEntry:
    text_value = _raw_to_text(raw)
    try:
        payload = json.loads(text_value)
    except json.JSONDecodeError:
        return CompletionDeadLetterEntry(index=index, malformed=True, error=text_value[:500])

    if not isinstance(payload, dict):
        return CompletionDeadLetterEntry(index=index, malformed=True, error=text_value[:500])

    nested_payload = payload.get("payload")
    return CompletionDeadLetterEntry(
        index=index,
        job_id=payload.get("job_id") if isinstance(payload.get("job_id"), str) else None,
        worker_id=payload.get("worker_id") if isinstance(payload.get("worker_id"), str) else None,
        url=payload.get("url") if isinstance(payload.get("url"), str) else None,
        payload=nested_payload if isinstance(nested_payload, dict) else {},
        error=payload.get("error") if isinstance(payload.get("error"), str) else None,
        status_code=payload.get("status_code") if isinstance(payload.get("status_code"), int) else None,
        attempts=payload.get("attempts") if isinstance(payload.get("attempts"), int) else None,
    )


async def _llen(redis: Any, key: str) -> int | None:
    try:
        value = await redis.llen(key)
        return int(value)
    except Exception as exc:  # noqa: BLE001 - status endpoint should degrade
        logger.debug("Unable to read Redis list length for %s: %s", key, exc)
        return None


async def _dead_letter_at(redis: Any, index: int) -> Any:
    rows = await redis.lrange(settings.job_completion_dead_letter_key, index, index)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Completion dead-letter entry not found.",
        )
    return rows[0]


async def _alembic_revision(db: AsyncSession) -> str | None:
    try:
        result = await db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        value = result.scalar_one_or_none()
        return str(value) if value else None
    except Exception as exc:  # noqa: BLE001 - local/test DBs may not have alembic_version
        logger.debug("Unable to read alembic revision: %s", exc)
        return None


@router.get("/status", response_model=OperationsStatusResponse)
async def get_operations_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Any, Depends(get_redis)],
    _admin: Annotated[JanuaUser, Depends(require_admin)],
) -> OperationsStatusResponse:
    """Return admin-only production readiness and queue status."""
    return OperationsStatusResponse(
        environment=settings.environment,
        app_version=settings.app_version,
        r2_configured=settings.r2_configured,
        janua_enabled=settings.janua_enabled,
        callback_token_configured=bool(settings.job_completion_callback_token),
        webhook_secret_configured=bool(settings.job_webhook_secret),
        alembic_revision=await _alembic_revision(db),
        redis={
            "reachable": True,
            "pending_jobs": await _llen(redis, "ceq:jobs:pending"),
            "processing_jobs": await _llen(redis, "ceq:jobs:processing"),
            "completion_dead_letters": await _llen(
                redis,
                settings.job_completion_dead_letter_key,
            ),
        },
    )


@router.get("/completion-dead-letters", response_model=CompletionDeadLetterListResponse)
async def list_completion_dead_letters(
    redis: Annotated[Any, Depends(get_redis)],
    _admin: Annotated[JanuaUser, Depends(require_admin)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> CompletionDeadLetterListResponse:
    """List exhausted worker completion callbacks retained in Redis."""
    raw_items = await redis.lrange(
        settings.job_completion_dead_letter_key,
        skip,
        skip + limit - 1,
    )
    return CompletionDeadLetterListResponse(
        redis_key=settings.job_completion_dead_letter_key,
        count=await _llen(redis, settings.job_completion_dead_letter_key),
        items=[
            _parse_dead_letter(raw_item, index=skip + offset)
            for offset, raw_item in enumerate(raw_items or [])
        ],
    )


@router.post(
    "/completion-dead-letters/{index}/replay",
    response_model=CompletionDeadLetterReplayResponse,
)
async def replay_completion_dead_letter(
    index: int,
    redis: Annotated[Any, Depends(get_redis)],
    _admin: Annotated[JanuaUser, Depends(require_admin)],
) -> CompletionDeadLetterReplayResponse:
    """Replay one exhausted worker completion callback and remove it on success."""
    if index < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="index must be greater than or equal to 0.",
        )
    if not settings.job_completion_callback_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JOB_COMPLETION_CALLBACK_TOKEN is not configured.",
        )

    raw_entry = await _dead_letter_at(redis, index)
    entry = _parse_dead_letter(raw_entry, index=index)
    if entry.malformed or not entry.url or not entry.payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dead-letter entry does not contain a replayable callback payload.",
        )

    async with httpx.AsyncClient(
        timeout=settings.job_completion_callback_timeout_seconds,
    ) as client:
        response = await client.post(
            entry.url,
            headers={"X-CEQ-Worker-Token": settings.job_completion_callback_token},
            json=entry.payload,
        )

    if not 200 <= response.status_code < 300:
        record_completion_dead_letter_replay("failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Replay callback was rejected upstream.",
                "upstream_status_code": response.status_code,
                "body": response.text[:500],
            },
        )

    removed_count = int(
        await redis.lrem(settings.job_completion_dead_letter_key, 1, raw_entry) or 0
    )
    if entry.job_id:
        await redis.hset(
            f"ceq:job:{entry.job_id}",
            mapping={
                "callback_dead_lettered": "false",
                "callback_replayed_at": datetime.now(UTC).isoformat(),
                "callback_replay_status": str(response.status_code),
            },
        )

    removed = removed_count > 0
    record_completion_dead_letter_replay("success" if removed else "orphaned")
    return CompletionDeadLetterReplayResponse(
        index=index,
        job_id=entry.job_id,
        status="replayed",
        upstream_status_code=response.status_code,
        removed=removed,
    )


@router.delete(
    "/completion-dead-letters/{index}",
    response_model=CompletionDeadLetterDiscardResponse,
)
async def discard_completion_dead_letter(
    index: int,
    redis: Annotated[Any, Depends(get_redis)],
    _admin: Annotated[JanuaUser, Depends(require_admin)],
) -> CompletionDeadLetterDiscardResponse:
    """Discard one dead-letter payload after an operator has handled it."""
    if index < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="index must be greater than or equal to 0.",
        )
    raw_entry = await _dead_letter_at(redis, index)
    removed_count = int(
        await redis.lrem(settings.job_completion_dead_letter_key, 1, raw_entry) or 0
    )
    return CompletionDeadLetterDiscardResponse(index=index, removed=removed_count > 0)
