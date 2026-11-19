"""Production submit API (``/v1/productions``, RFC 0061 Q7).

A named service client submits a small graph of CPU jobs and reads its state.
There is no human path here: the studio's view of productions is a later
surface with its own authorization.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth.janua import JanuaUser, get_production_principal
from ceq_api.config import get_settings
from ceq_api.db.redis import get_redis
from ceq_api.db.session import get_db
from ceq_api.models.job import Job, JobStatus
from ceq_api.models.production import Production
from ceq_api.productions import (
    PRODUCTION_KINDS,
    TERMINAL,
    GraphError,
    cancel_production,
    in_submitted_order,
    production_status,
    release_ready_jobs,
    validate_graph,
)
from ceq_api.routers.jobs import _remove_pending_job

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

MAX_PARAMS_BYTES = 16 * 1024
MAX_STEPS = 100
STEP_NAME = r"^[a-z0-9][a-z0-9._-]{0,63}$"


class ProductionStep(BaseModel):
    """One job of a production."""

    step: str = Field(pattern=STEP_NAME, description="Name of the step, unique in the production")
    kind: str = Field(description=f"One of: {', '.join(sorted(PRODUCTION_KINDS))}")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Handed to the worker as given. A capture step needs `url`.",
    )
    depends_on: list[Annotated[str, Field(pattern=STEP_NAME)]] = Field(
        default_factory=list,
        max_length=MAX_STEPS,
        description="Steps that must complete first. Their outputs are passed to this step.",
    )

    @field_validator("params")
    @classmethod
    def _params_are_small(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value)) > MAX_PARAMS_BYTES:
            raise ValueError(f"params must serialize to at most {MAX_PARAMS_BYTES} bytes")
        return value


class ProductionCreate(BaseModel):
    # Printable characters only: a control character would be refused by the
    # database at write time, as a 500.
    name: str = Field(min_length=1, max_length=120, pattern=r"^[^\x00-\x1f\x7f]+$")
    # A hard ceiling so an oversized list is refused before each step is
    # validated; the configured limit (PRODUCTION_MAX_JOBS) is applied after.
    steps: list[ProductionStep] = Field(min_length=1, max_length=MAX_STEPS)


class ProductionJobResponse(BaseModel):
    id: UUID
    step: str
    kind: str
    status: str
    waiting: bool = Field(description="True while the step waits on another step")
    depends_on: list[str]
    progress: float
    error: str | None
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ProductionResponse(BaseModel):
    id: UUID
    name: str
    status: str = Field(
        description="Read from the jobs: queued | running | completed | failed | cancelled"
    )
    created_at: datetime
    jobs: list[ProductionJobResponse]


def _response(production: Production, jobs: list[Job]) -> ProductionResponse:
    return ProductionResponse(
        id=production.id,
        name=production.name,
        status=production_status(jobs),
        created_at=production.created_at,
        jobs=[
            ProductionJobResponse(
                id=job.id,
                step=job.step or "",
                kind=job.kind,
                status=job.status,
                waiting=job.status == JobStatus.QUEUED.value and job.released_at is None,
                depends_on=list(job.depends_on or []),
                progress=job.progress,
                error=job.error,
                queued_at=job.queued_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
            )
            for job in jobs
        ],
    )


async def _jobs_of(db: AsyncSession, production_id: UUID) -> list[Job]:
    result = await db.execute(select(Job).where(Job.production_id == production_id))
    spec = (
        await db.execute(select(Production.spec).where(Production.id == production_id))
    ).scalar_one_or_none()
    return in_submitted_order(list(result.scalars().all()), spec)


@router.post("/", response_model=ProductionResponse, status_code=status.HTTP_201_CREATED)
async def submit_production(
    data: ProductionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[JanuaUser, Depends(get_production_principal)],
) -> ProductionResponse:
    """Submit a production: a small graph of capture, edit and export jobs.

    Steps with no dependency are queued at once. Every other step waits until
    the steps it names have completed, then is queued with their outputs. If a
    step fails or is cancelled, the steps that needed it are cancelled.
    """
    steps = [step.model_dump() for step in data.steps]
    try:
        order = validate_graph(
            steps,
            allowed_hosts=settings.production_allowed_hosts,
            max_jobs=settings.production_max_jobs,
        )
    except GraphError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None

    # One client may not pile up unfinished productions without bound.
    active = await db.execute(
        select(Job.production_id)
        .join(Production, Production.id == Job.production_id)
        .where(
            Production.client_id == (principal.client_id or ""),
            Job.status.notin_(TERMINAL),
        )
        .distinct()
    )
    if len(active.all()) >= settings.production_max_active_per_client:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "This client already has "
                f"{settings.production_max_active_per_client} unfinished productions."
            ),
        )

    now = datetime.now(UTC)
    production = Production(
        id=uuid4(),
        name=data.name,
        user_id=principal.id,
        client_id=principal.client_id or "",
        spec={"name": data.name, "steps": steps},
    )
    db.add(production)
    await db.flush()

    by_name = {step["step"]: step for step in steps}
    for name in order:
        step = by_name[name]
        db.add(
            Job(
                id=uuid4(),
                kind=step["kind"],
                workflow_id=None,
                user_id=principal.id,
                production_id=production.id,
                step=name,
                depends_on=list(step["depends_on"]),
                status=JobStatus.QUEUED.value,
                input_params=step["params"],
                queued_at=now,
            )
        )
    await db.flush()
    await release_ready_jobs(db, production.id)
    await db.refresh(production)

    logger.info(
        "Production %s (%r) submitted by %s: %s steps",
        production.id,
        production.name,
        principal.client_id,
        len(steps),
    )
    return _response(production, await _jobs_of(db, production.id))


@router.get("/{production_id}", response_model=ProductionResponse)
async def get_production(
    production_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[JanuaUser, Depends(get_production_principal)],
) -> ProductionResponse:
    """Read a production and the state of each of its jobs.

    A client sees only what it submitted; anything else is a 404, so the
    route does not reveal that another client's production exists.
    """
    result = await db.execute(select(Production).where(Production.id == production_id))
    production = result.scalar_one_or_none()
    if production is None or production.client_id != (principal.client_id or ""):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Production not found.")
    # Reading also repairs: a step whose dependencies are complete but which
    # was never queued (the API died between the two) is queued now. Releasing
    # is idempotent, so this is safe to do on every read.
    await release_ready_jobs(db, production.id)
    return _response(production, await _jobs_of(db, production.id))


@router.delete("/{production_id}", response_model=ProductionResponse)
async def cancel_production_route(
    production_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[JanuaUser, Depends(get_production_principal)],
) -> ProductionResponse:
    """Cancel every unfinished job of a production the caller submitted.

    Waiting steps end at once. A step already queued is pulled from its queue;
    a running one is signalled, exactly as ``DELETE /v1/jobs/{id}`` does.
    Cancelling a finished production changes nothing.
    """
    result = await db.execute(select(Production).where(Production.id == production_id))
    production = result.scalar_one_or_none()
    if production is None or production.client_id != (principal.client_id or ""):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Production not found.")

    cancelled = await cancel_production(db, production.id)
    # Database first (above), queue and worker signals after: these are not
    # undone by a rollback, so they come last.
    released = [job for job in cancelled if job.released_at is not None]
    if released:
        redis = get_redis()
        now = datetime.now(UTC).isoformat()
        for job in released:
            await redis.hset(
                f"ceq:job:{job.id}",
                mapping={"status": JobStatus.CANCELLED.value, "cancel_requested": "true"},
            )
            await redis.publish(
                f"ceq:job:{job.id}:control",
                json.dumps({"action": "cancel", "job_id": str(job.id), "requested_at": now}),
            )
            await _remove_pending_job(redis, job.id, job.kind)
    logger.info(
        "Production %s cancelled by %s: %s jobs", production.id, principal.client_id, len(cancelled)
    )
    return _response(production, await _jobs_of(db, production.id))
