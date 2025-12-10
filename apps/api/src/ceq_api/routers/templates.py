"""Template management endpoints."""

from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from jsonschema import Draft7Validator
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth import JanuaUser, get_current_user
from ceq_api.db import get_db
from ceq_api.db.redis import enqueue_job
from ceq_api.models import Job, Template, Workflow

router = APIRouter()


# === Pydantic Models ===


class TemplateResponse(BaseModel):
    """Response model for a template."""

    id: UUID
    name: str
    description: str | None
    category: str = Field(description="social | video | 3d | utility")
    workflow_json: dict[str, Any]
    input_schema: dict[str, Any]
    thumbnail_url: str | None
    preview_urls: list[str]
    tags: list[str]
    model_requirements: list[str]
    vram_requirement_gb: int
    fork_count: int
    run_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TemplateListResponse(BaseModel):
    """Paginated template list."""

    templates: list[TemplateResponse]
    total: int
    skip: int
    limit: int


class ForkTemplateRequest(BaseModel):
    """Request to fork a template into a workflow."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None


class ForkTemplateResponse(BaseModel):
    """Response after forking a template."""

    workflow_id: UUID
    name: str
    message: str


class RunTemplateRequest(BaseModel):
    """Request to run a template directly."""

    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Input parameters matching template's input_schema",
    )
    priority: int = Field(default=0, ge=0, le=10, description="Job priority (0-10)")
    webhook_url: str | None = Field(
        default=None,
        description="URL to POST results when job completes",
    )


class RunTemplateResponse(BaseModel):
    """Response after running a template."""

    job_id: UUID
    workflow_id: UUID
    status: str
    message: str


# === Template Categories ===

TEMPLATE_CATEGORIES = {
    "social": {
        "name": "Social Media",
        "description": "Automated content generation for social platforms",
        "icon": "📱",
    },
    "video": {
        "name": "Video Clone",
        "description": "AI-generated spokesperson and video content",
        "icon": "🎬",
    },
    "3d": {
        "name": "3D Rendering",
        "description": "Product visualization and 3D asset generation",
        "icon": "🧊",
    },
    "utility": {
        "name": "Utility",
        "description": "Image processing, upscaling, and enhancement",
        "icon": "🔧",
    },
}


# === Endpoints ===


@router.get("/", response_model=TemplateListResponse)
async def list_templates(
    db: Annotated[AsyncSession, Depends(get_db)],
    category: str | None = Query(None, description="Filter by category"),
    tag: str | None = Query(None, description="Filter by tag"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> TemplateListResponse:
    """
    List available templates.

    Browse the spell library. Public access - no authentication required.
    """
    # Build query
    query = select(Template)

    # Filter by category
    if category:
        if category not in TEMPLATE_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category. Must be one of: {', '.join(TEMPLATE_CATEGORIES.keys())}",
            )
        query = query.where(Template.category == category)

    # Filter by tag
    if tag:
        query = query.where(Template.tags.contains([tag]))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Fetch page
    query = query.order_by(Template.run_count.desc(), Template.created_at.desc())
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    templates = list(result.scalars().all())

    return TemplateListResponse(
        templates=[TemplateResponse.model_validate(t) for t in templates],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/categories")
async def list_categories() -> dict[str, Any]:
    """
    List template categories.

    The schools of transmutation.
    """
    return {
        "categories": TEMPLATE_CATEGORIES,
    }


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Template:
    """
    Get a template by ID.

    Study a specific spell.
    """
    query = select(Template).where(Template.id == template_id)
    result = await db.execute(query)
    template = result.scalar_one_or_none()

    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found in the grimoire.",
        )

    return template


@router.post("/{template_id}/fork", response_model=ForkTemplateResponse)
async def fork_template(
    template_id: UUID,
    data: ForkTemplateRequest,
    user: Annotated[JanuaUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ForkTemplateResponse:
    """
    Fork a template into your own workflow.

    Copy the spell to your grimoire for customization.
    """
    # Get template
    query = select(Template).where(Template.id == template_id)
    result = await db.execute(query)
    template = result.scalar_one_or_none()

    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found in the grimoire.",
        )

    # Create workflow from template
    workflow_name = data.name or f"{template.name} (forked)"
    workflow = Workflow(
        name=workflow_name,
        description=data.description or template.description,
        workflow_json=template.workflow_json,
        input_schema=template.input_schema,
        tags=template.tags.copy(),
        user_id=user.id,
        org_id=user.org_id,
        template_id=template.id,
        is_public=False,
    )

    db.add(workflow)

    # Increment fork count
    template.fork_count += 1

    await db.flush()
    await db.refresh(workflow)

    return ForkTemplateResponse(
        workflow_id=workflow.id,
        name=workflow.name,
        message="Spell inscribed to your grimoire. ✨",
    )


@router.post("/{template_id}/run", response_model=RunTemplateResponse)
async def run_template(
    template_id: UUID,
    data: RunTemplateRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[JanuaUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RunTemplateResponse:
    """
    Run a template directly without forking.

    Execute the spell as-is with custom parameters.
    Creates a temporary workflow and queues execution.
    """
    # Get template
    query = select(Template).where(Template.id == template_id)
    result = await db.execute(query)
    template = result.scalar_one_or_none()

    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found in the grimoire.",
        )

    # Validate params against input_schema
    if template.input_schema:
        try:
            validator = Draft7Validator(template.input_schema)
            errors = list(validator.iter_errors(data.params))
            if errors:
                error_messages = [
                    f"{'.'.join(str(p) for p in e.path)}: {e.message}" if e.path else e.message
                    for e in errors[:5]
                ]
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "message": "Parameters failed entropy validation.",
                        "errors": error_messages,
                    },
                )
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            # Schema itself may be malformed - log and continue
            pass

    # Create ephemeral workflow for this run
    now = datetime.now(timezone.utc)
    workflow = Workflow(
        name=f"[Run] {template.name}",
        description=f"Direct run of template: {template.name}",
        workflow_json=template.workflow_json,
        input_schema=template.input_schema,
        tags=["ephemeral", "template-run"],
        user_id=user.id,
        org_id=user.org_id,
        template_id=template.id,
        is_public=False,
    )

    db.add(workflow)
    await db.flush()
    await db.refresh(workflow)

    # Create job record
    job = Job(
        workflow_id=workflow.id,
        user_id=user.id,
        status="queued",
        input_params=data.params,
        priority=data.priority,
        webhook_url=data.webhook_url,
        queued_at=now,
    )

    db.add(job)

    # Increment run count
    template.run_count += 1

    await db.flush()
    await db.refresh(job)

    # Queue job for processing
    job_data = {
        "id": str(job.id),
        "workflow_id": str(workflow.id),
        "template_id": str(template.id),
        "input": {
            "workflow_json": workflow.workflow_json,
            "params": data.params,
            "job_id": str(job.id),
            "webhook_url": data.webhook_url,
        },
    }

    background_tasks.add_task(enqueue_job, job_data)

    return RunTemplateResponse(
        job_id=job.id,
        workflow_id=workflow.id,
        status="queued",
        message="In the crucible... Your transmutation is queued. 🔥",
    )
