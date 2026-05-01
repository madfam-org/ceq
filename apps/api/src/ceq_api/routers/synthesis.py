"""
Synthesis Router — Zero-Results Generative Fallback

When Blueprint Harvester registers a "zero-results" search query, it POSTs
to this endpoint. CEQ immediately enqueues a TripoSR (or Hunyuan3D) generation
job to synthesise a brand-new, royalty-free 3D asset from the user's text prompt.

POST /v1/synthesis/from_query
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth import JanuaUser, get_current_user
from ceq_api.db import get_db
from ceq_api.db.redis import enqueue_job
from ceq_api.models import Job, Template

logger = logging.getLogger(__name__)

router = APIRouter()

# The canonical CEQ template slug for text-to-3D synthesis.
# Must exist in the templates table (seeded via seed_templates.py).
_TEXT_TO_3D_TEMPLATE_SLUG = "triposr-text-to-3d"


# ── Schemas ────────────────────────────────────────────────────────────────────


class ZeroResultsSynthesisRequest(BaseModel):
    """
    Payload sent by Blueprint Harvester when a search returns zero results.
    CEQ uses this to enqueue an on-demand generative 3D job.
    """

    prompt: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="The original user search query / text prompt for 3D synthesis.",
    )
    source_query: str = Field(
        ...,
        description="The raw search string that returned zero results (for provenance tracking).",
    )
    source_platform: str = Field(
        default="blueprint-harvester",
        description="Platform that triggered the synthesis request.",
    )
    preferred_format: str = Field(
        default="glb",
        description="Preferred output format: 'glb', 'obj', or 'stl'.",
    )
    webhook_url: str | None = Field(
        default=None,
        description="URL to POST the completed asset when synthesis finishes.",
    )


class SynthesisResponse(BaseModel):
    job_id: UUID
    status: str
    prompt: str
    source_query: str
    message: str
    estimated_seconds: int = 45


# ── Endpoint ───────────────────────────────────────────────────────────────────


@router.post(
    "/from_query",
    response_model=SynthesisResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Zero-results generative 3D fallback",
    description=(
        "Triggered by Blueprint Harvester when a search returns zero results. "
        "Enqueues a TripoSR text-to-3D job and returns a job ID for polling. "
        "The completed asset URL is also sent to webhook_url if provided."
    ),
)
async def synthesize_from_query(
    data: ZeroResultsSynthesisRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[JanuaUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SynthesisResponse:
    """Enqueue a generative 3D synthesis job triggered by a zero-results search."""

    # 1. Resolve the text-to-3D template
    result = await db.execute(
        select(Template).where(
            Template.slug == _TEXT_TO_3D_TEMPLATE_SLUG,
            Template.is_deleted == False,  # noqa: E712
        )
    )
    template = result.scalar_one_or_none()

    if template is None:
        logger.error(
            "text-to-3D template '%s' not found in database. "
            "Run seed_templates.py to populate.",
            _TEXT_TO_3D_TEMPLATE_SLUG,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Synthesis template '{_TEXT_TO_3D_TEMPLATE_SLUG}' is not available. "
                "Contact your administrator to seed the template catalogue."
            ),
        )

    # 2. Create a CEQ job record
    now = datetime.now(UTC)
    job = Job(
        user_id=user.id,
        status="queued",
        input_params={
            "prompt": data.prompt,
            "source_query": data.source_query,
            "source_platform": data.source_platform,
            "preferred_format": data.preferred_format,
            "synthesis_trigger": "zero_results",
        },
        priority=5,  # Medium-high priority — user is actively waiting
        webhook_url=data.webhook_url,
        queued_at=now,
    )

    db.add(job)
    await db.flush()
    await db.refresh(job)

    # 3. Enqueue for GPU execution
    job_data: dict[str, Any] = {
        "id": str(job.id),
        "input": {
            "template": {
                "slug": template.slug,
                "workflow_json": template.workflow_json,
                "model_requirements": template.model_requirements or [],
                "vram_requirement_gb": template.vram_requirement_gb or 16,
                "category": "3d",
            },
            "params": {
                "prompt": data.prompt,
                "output_format": data.preferred_format,
            },
            "job_id": str(job.id),
            "webhook_url": data.webhook_url,
        },
    }
    background_tasks.add_task(enqueue_job, job_data)

    logger.info(
        "Synthesis job enqueued",
        extra={
            "job_id": str(job.id),
            "prompt": data.prompt[:80],
            "source": data.source_platform,
        },
    )

    return SynthesisResponse(
        job_id=job.id,
        status="queued",
        prompt=data.prompt,
        source_query=data.source_query,
        message=(
            "Synthesis queued. CEQ is generating a royalty-free 3D asset from your prompt. "
            "Poll /v1/jobs/{job_id} for status or await webhook delivery."
        ),
    )
