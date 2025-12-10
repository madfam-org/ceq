"""Workflow management endpoints."""

from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth import JanuaUser, get_current_user
from ceq_api.db import get_db
from ceq_api.db.redis import enqueue_job
from ceq_api.models import Job, Workflow

router = APIRouter()


# === Pydantic Models ===


class WorkflowCreate(BaseModel):
    """Request model for creating a workflow."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    workflow_json: dict[str, Any] = Field(..., description="ComfyUI workflow in API format")
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for workflow inputs",
    )
    tags: list[str] = Field(default_factory=list)
    is_public: bool = False


class WorkflowUpdate(BaseModel):
    """Request model for updating a workflow."""

    name: str | None = None
    description: str | None = None
    workflow_json: dict[str, Any] | None = None
    input_schema: dict[str, Any] | None = None
    tags: list[str] | None = None
    is_public: bool | None = None


class WorkflowResponse(BaseModel):
    """Response model for a workflow."""

    id: UUID
    name: str
    description: str | None
    workflow_json: dict[str, Any]
    input_schema: dict[str, Any]
    tags: list[str]
    template_id: UUID | None
    is_public: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowListResponse(BaseModel):
    """Paginated workflow list."""

    workflows: list[WorkflowResponse]
    total: int
    skip: int
    limit: int


class WorkflowRunRequest(BaseModel):
    """Request model for running a workflow."""

    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Input parameters matching workflow's input_schema",
    )
    priority: int = Field(default=0, ge=0, le=10, description="Job priority (0-10)")
    webhook_url: str | None = Field(
        default=None,
        description="URL to POST results when job completes",
    )


class WorkflowRunResponse(BaseModel):
    """Response model for workflow execution."""

    job_id: UUID
    status: str
    message: str


# === Endpoints ===


@router.post("/", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    data: WorkflowCreate,
    user: Annotated[JanuaUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Workflow:
    """
    Create a new workflow.

    Quantizes your creative entropy into a reproducible workflow.
    """
    workflow = Workflow(
        name=data.name,
        description=data.description,
        workflow_json=data.workflow_json,
        input_schema=data.input_schema,
        tags=data.tags,
        is_public=data.is_public,
        user_id=user.id,
        org_id=user.org_id,
    )

    db.add(workflow)
    await db.flush()
    await db.refresh(workflow)

    return workflow


@router.get("/", response_model=WorkflowListResponse)
async def list_workflows(
    user: Annotated[JanuaUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    tag: str | None = None,
    public_only: bool = False,
) -> WorkflowListResponse:
    """
    List workflows.

    Browse your collection of quantized entropy.
    """
    # Base query - user's own workflows
    query = select(Workflow).where(
        Workflow.is_deleted == False,  # noqa: E712
    )

    if public_only:
        query = query.where(Workflow.is_public == True)  # noqa: E712
    else:
        # Own workflows + public workflows
        query = query.where(
            (Workflow.user_id == user.id) | (Workflow.is_public == True)  # noqa: E712
        )

    # Filter by tag
    if tag:
        query = query.where(Workflow.tags.contains([tag]))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Fetch page
    query = query.order_by(Workflow.updated_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    workflows = list(result.scalars().all())

    return WorkflowListResponse(
        workflows=workflows,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: UUID,
    user: Annotated[JanuaUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Workflow:
    """
    Get a workflow by ID.

    Retrieve a specific entropy pattern.
    """
    query = select(Workflow).where(
        Workflow.id == workflow_id,
        Workflow.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(query)
    workflow = result.scalar_one_or_none()

    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found in latent space.",
        )

    # Check access
    if not workflow.is_public and workflow.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This entropy pattern is private.",
        )

    return workflow


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: UUID,
    data: WorkflowUpdate,
    user: Annotated[JanuaUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Workflow:
    """
    Update a workflow.

    Refine your entropy pattern.
    """
    query = select(Workflow).where(
        Workflow.id == workflow_id,
        Workflow.user_id == user.id,
        Workflow.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(query)
    workflow = result.scalar_one_or_none()

    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found or not owned by you.",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(workflow, field, value)

    await db.flush()
    await db.refresh(workflow)

    return workflow


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: UUID,
    user: Annotated[JanuaUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """
    Delete a workflow.

    Release entropy back into the void.
    """
    query = select(Workflow).where(
        Workflow.id == workflow_id,
        Workflow.user_id == user.id,
        Workflow.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(query)
    workflow = result.scalar_one_or_none()

    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found or not owned by you.",
        )

    # Soft delete
    workflow.is_deleted = True
    await db.flush()


@router.post("/{workflow_id}/run", response_model=WorkflowRunResponse)
async def run_workflow(
    workflow_id: UUID,
    data: WorkflowRunRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[JanuaUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkflowRunResponse:
    """
    Execute a workflow.

    Materialize your vision from the latent space.

    This endpoint queues the workflow for execution on a GPU worker.
    Use the returned job_id to track progress via /v1/jobs/{job_id}.
    """
    # Get workflow
    query = select(Workflow).where(
        Workflow.id == workflow_id,
        Workflow.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(query)
    workflow = result.scalar_one_or_none()

    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found in latent space.",
        )

    # Check access
    if not workflow.is_public and workflow.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This entropy pattern is private.",
        )

    # TODO: Validate params against input_schema

    # Create job record
    now = datetime.now(timezone.utc)
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
    await db.flush()
    await db.refresh(job)

    # Queue job for processing
    job_data = {
        "id": str(job.id),
        "workflow_id": str(workflow.id),
        "input": {
            "workflow_json": workflow.workflow_json,
            "params": data.params,
            "job_id": str(job.id),
            "webhook_url": data.webhook_url,
        },
    }

    background_tasks.add_task(enqueue_job, job_data)

    return WorkflowRunResponse(
        job_id=job.id,
        status="queued",
        message="In the crucible... Your transmutation is queued.",
    )
