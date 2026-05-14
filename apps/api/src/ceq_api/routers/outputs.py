"""Output management endpoints with R2 storage integration."""

import logging
import re
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth import JanuaUser, get_current_user
from ceq_api.db import get_db
from ceq_api.models import Job, Output
from ceq_api.storage import StorageClient, get_storage

logger = logging.getLogger(__name__)

router = APIRouter()


# === Pydantic Models ===


class OutputResponse(BaseModel):
    """Response model for an output."""

    id: UUID
    job_id: UUID
    filename: str
    storage_uri: str
    public_url: str = Field(description="Direct public URL for the output")
    file_type: str = Field(description="MIME type for the output")
    file_size_bytes: int
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    preview_url: str | None = None
    metadata: dict[str, Any]
    published_to: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OutputListResponse(BaseModel):
    """Paginated output list."""

    outputs: list[OutputResponse]
    total: int
    skip: int
    limit: int


class DownloadUrlResponse(BaseModel):
    """Presigned download URL response."""

    download_url: str
    expires_in: int = Field(description="URL expiration in seconds")
    filename: str


class UploadUrlRequest(BaseModel):
    """Request for a presigned upload URL."""

    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(
        default="application/octet-stream",
        description="MIME type of the file",
    )
    job_id: UUID = Field(description="Job this output belongs to")
    output_type: str | None = Field(
        default=None,
        description="Deprecated category field retained for older clients",
    )


class UploadUrlResponse(BaseModel):
    """Presigned upload URL response."""

    upload_url: str
    storage_uri: str
    expires_in: int = Field(description="URL expiration in seconds")


class RegisterOutputRequest(BaseModel):
    """Request to register a completed upload as an output."""

    job_id: UUID
    storage_uri: str
    filename: str | None = Field(default=None, min_length=1, max_length=255)
    file_type: str | None = Field(default=None, description="MIME type for the file")
    file_size_bytes: int = Field(default=0, ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    duration_seconds: float | None = Field(default=None, ge=0)
    preview_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    output_type: str | None = Field(
        default=None,
        description="Deprecated category field retained for older clients",
    )
    thumbnail_uri: str | None = Field(
        default=None,
        description="Deprecated preview storage URI retained for older clients",
    )


class PublishRequest(BaseModel):
    """Request to publish an output."""

    channel: str = Field(description="twitter | instagram | linkedin | discord | webhook")
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Channel-specific options (caption, hashtags, etc.)",
    )


class PublishResponse(BaseModel):
    """Response after publishing."""

    success: bool
    channel: str
    url: str | None
    message: str


# === Publishing Channels ===

PUBLISH_CHANNELS = {
    "twitter": {
        "name": "Twitter/X",
        "description": "Post to Twitter/X",
        "icon": "🐦",
        "supported_types": ["image", "video"],
        "status": "coming_soon",
    },
    "instagram": {
        "name": "Instagram",
        "description": "Post to Instagram",
        "icon": "📸",
        "supported_types": ["image", "video"],
        "status": "coming_soon",
    },
    "linkedin": {
        "name": "LinkedIn",
        "description": "Post to LinkedIn",
        "icon": "💼",
        "supported_types": ["image", "video"],
        "status": "coming_soon",
    },
    "discord": {
        "name": "Discord",
        "description": "Post to Discord webhook",
        "icon": "🎮",
        "supported_types": ["image", "video"],
        "status": "coming_soon",
    },
    "webhook": {
        "name": "Custom Webhook",
        "description": "POST to a custom URL",
        "icon": "🔗",
        "supported_types": ["image", "video", "model"],
        "status": "available",
    },
}

LEGACY_OUTPUT_TYPES = {"image", "video", "model"}


# === Helper Functions ===


def _safe_filename(filename: str) -> str:
    """Constrain user-provided filenames to object-key safe text."""
    normalized = filename.replace("/", "_").replace("\\", "_").replace("\x00", "")
    normalized = re.sub(r"[^a-zA-Z0-9_.-]", "_", normalized).lstrip(".")
    return normalized[:255] or "output"


def _filename_from_uri(storage_uri: str) -> str:
    filename = storage_uri.rstrip("/").rsplit("/", 1)[-1]
    return _safe_filename(filename or "output")


def _legacy_output_type_to_mime(output_type: str | None) -> str:
    if output_type == "image":
        return "image/png"
    if output_type == "video":
        return "video/mp4"
    if output_type == "model":
        return "model/gltf-binary"
    return "application/octet-stream"


def _output_category(file_type: str) -> str:
    if file_type.startswith("image/"):
        return "image"
    if file_type.startswith("video/"):
        return "video"
    if file_type.startswith("model/"):
        return "model"
    return "file"


def _enrich_output_response(
    output: Output,
    storage: StorageClient,
) -> dict[str, Any]:
    """Add public URLs to output response."""
    return {
        "id": output.id,
        "job_id": output.job_id,
        "filename": output.filename,
        "storage_uri": output.storage_uri,
        "public_url": storage.get_public_url(output.storage_uri),
        "file_type": output.file_type,
        "file_size_bytes": output.file_size_bytes,
        "width": output.width,
        "height": output.height,
        "duration_seconds": output.duration_seconds,
        "preview_url": output.preview_url,
        "metadata": output.output_metadata,
        "published_to": output.published_to,
        "created_at": output.created_at,
        "updated_at": output.updated_at,
    }


# === Endpoints ===


@router.get("/", response_model=OutputListResponse)
async def list_outputs(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
    job_id: UUID | None = Query(None, description="Filter by job ID"),  # noqa: B008
    file_type: str | None = Query(None, description="Filter by MIME type or type prefix"),
    output_type: str | None = Query(None, description="Deprecated filter: image | video | model"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> OutputListResponse:
    """
    List generated outputs.

    Browse your materialized creations.
    """
    storage = await get_storage()

    # Build query - outputs belong to user's jobs
    query = (
        select(Output)
        .join(Job, Output.job_id == Job.id)
        .where(Job.user_id == user.id)
    )

    # Filter by job
    if job_id:
        query = query.where(Output.job_id == job_id)

    # Filter by type. `output_type` is retained as a category alias for older clients.
    if output_type:
        if output_type not in LEGACY_OUTPUT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid output_type. Must be one of: {', '.join(LEGACY_OUTPUT_TYPES)}",
            )
        file_type = f"{output_type}/"

    if file_type:
        file_type_filter = (
            Output.file_type.startswith(file_type)
            if file_type.endswith("/")
            else Output.file_type == file_type
        )
        query = query.where(file_type_filter)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Fetch page
    query = query.order_by(Output.created_at.desc())
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    outputs = list(result.scalars().all())

    return OutputListResponse(
        outputs=[
            OutputResponse(**_enrich_output_response(o, storage))
            for o in outputs
        ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/channels")
async def list_publish_channels() -> dict[str, Any]:
    """
    List available publishing channels.

    Where to broadcast your creations.
    """
    return {
        "channels": PUBLISH_CHANNELS,
    }


@router.post("/upload-url", response_model=UploadUrlResponse)
async def get_upload_url(
    data: UploadUrlRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> UploadUrlResponse:
    """
    Get a presigned URL for direct upload to R2.

    Prepare the crucible for your creation.
    """
    storage = await get_storage()

    if not storage.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage not configured. The crucible is offline.",
        )

    if data.output_type and data.output_type not in LEGACY_OUTPUT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid output_type. Must be one of: {', '.join(LEGACY_OUTPUT_TYPES)}",
        )

    # Verify job belongs to user
    job_query = select(Job).where(Job.id == data.job_id, Job.user_id == user.id)
    result = await db.execute(job_query)
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or access denied.",
        )

    # Generate key with timestamp for uniqueness
    from uuid import uuid4
    unique_id = uuid4().hex[:8]
    key = f"outputs/{data.job_id}/{unique_id}_{_safe_filename(data.filename)}"

    expires_in = 3600  # 1 hour

    upload_data = await storage.generate_upload_url(
        key=key,
        content_type=data.content_type,
        expires_in=expires_in,
    )

    return UploadUrlResponse(
        upload_url=upload_data["upload_url"],
        storage_uri=upload_data["storage_uri"],
        expires_in=expires_in,
    )


@router.post("/register", response_model=OutputResponse)
async def register_output(
    data: RegisterOutputRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> OutputResponse:
    """
    Register a completed upload as an output.

    Manifest the creation into existence.
    """
    storage = await get_storage()

    if data.output_type and data.output_type not in LEGACY_OUTPUT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid output_type. Must be one of: {', '.join(LEGACY_OUTPUT_TYPES)}",
        )

    # Verify job belongs to user
    job_query = select(Job).where(Job.id == data.job_id, Job.user_id == user.id)
    result = await db.execute(job_query)
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or access denied.",
        )

    filename = _safe_filename(data.filename) if data.filename else _filename_from_uri(data.storage_uri)
    file_type = data.file_type or _legacy_output_type_to_mime(data.output_type)
    preview_url = data.preview_url
    if preview_url is None and data.thumbnail_uri:
        preview_url = storage.get_public_url(data.thumbnail_uri)

    # Create output record
    output = Output(
        job_id=data.job_id,
        user_id=user.id,
        filename=filename,
        storage_uri=data.storage_uri,
        file_type=file_type,
        file_size_bytes=data.file_size_bytes,
        width=data.width,
        height=data.height,
        duration_seconds=data.duration_seconds,
        preview_url=preview_url,
        output_metadata=data.metadata,
        published_to=[],
    )

    db.add(output)
    await db.flush()
    await db.refresh(output)

    return OutputResponse(**_enrich_output_response(output, storage))


@router.get("/{output_id}", response_model=OutputResponse)
async def get_output(
    output_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> OutputResponse:
    """
    Get an output by ID.

    Examine a specific creation.
    """
    storage = await get_storage()

    # Get output with job ownership check
    query = (
        select(Output)
        .join(Job, Output.job_id == Job.id)
        .where(Output.id == output_id, Job.user_id == user.id)
    )
    result = await db.execute(query)
    output = result.scalar_one_or_none()

    if output is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output not found or access denied.",
        )

    return OutputResponse(**_enrich_output_response(output, storage))


@router.get("/{output_id}/download", response_model=DownloadUrlResponse)
async def get_download_url(
    output_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
    expires_in: int = Query(3600, ge=60, le=86400, description="URL expiration in seconds"),
) -> DownloadUrlResponse:
    """
    Get a presigned download URL for an output.

    Summon the creation for download.
    """
    storage = await get_storage()

    # Get output with job ownership check
    query = (
        select(Output)
        .join(Job, Output.job_id == Job.id)
        .where(Output.id == output_id, Job.user_id == user.id)
    )
    result = await db.execute(query)
    output = result.scalar_one_or_none()

    if output is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output not found or access denied.",
        )

    download_url = await storage.generate_download_url(
        storage_uri=output.storage_uri,
        expires_in=expires_in,
        filename=output.filename,
    )

    return DownloadUrlResponse(
        download_url=download_url,
        expires_in=expires_in,
        filename=output.filename,
    )


@router.post("/{output_id}/publish", response_model=PublishResponse)
async def publish_output(
    output_id: UUID,
    data: PublishRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> PublishResponse:
    """
    Publish an output to a channel.

    Broadcast your creation to the world.
    """
    storage = await get_storage()

    # Validate channel
    if data.channel not in PUBLISH_CHANNELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid channel. Must be one of: {', '.join(PUBLISH_CHANNELS.keys())}",
        )

    channel_info = PUBLISH_CHANNELS[data.channel]

    # Check if channel is available
    if channel_info.get("status") == "coming_soon":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"{channel_info['name']} publishing coming soon. The portal is charging...",
        )

    # Get output with job ownership check
    query = (
        select(Output)
        .join(Job, Output.job_id == Job.id)
        .where(Output.id == output_id, Job.user_id == user.id)
    )
    result = await db.execute(query)
    output = result.scalar_one_or_none()

    if output is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output not found or access denied.",
        )

    output_category = _output_category(output.file_type)

    # Check if output type is supported by channel
    if output_category not in channel_info["supported_types"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{channel_info['name']} does not support {output.file_type} outputs.",
        )

    # Handle webhook publishing
    if data.channel == "webhook":
        webhook_url = data.options.get("url")
        if not webhook_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook URL is required in options.url",
            )

        # POST to webhook (fire and forget for now)
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook_url,
                    json={
                        "output_id": str(output.id),
                        "job_id": str(output.job_id),
                        "filename": output.filename,
                        "file_type": output.file_type,
                        "storage_uri": output.storage_uri,
                        "url": storage.get_public_url(output.storage_uri),
                        "metadata": output.output_metadata,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as e:
            return PublishResponse(
                success=False,
                channel=data.channel,
                url=webhook_url,
                message=f"Webhook failed: {str(e)}",
            )

        # Record successful publish
        publish_record = {
            "channel": data.channel,
            "url": webhook_url,
            "published_at": datetime.now(UTC).isoformat(),
        }
        output.published_to = [*output.published_to, publish_record]
        await db.flush()

        return PublishResponse(
            success=True,
            channel=data.channel,
            url=webhook_url,
            message="Creation broadcasted via webhook. ✨",
        )

    # Other channels not yet implemented
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"{channel_info['name']} publishing coming soon. The portal is charging...",
    )


@router.delete("/{output_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_output(
    output_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> None:
    """
    Delete an output.

    Return creation to the void.
    """
    storage = await get_storage()

    # Get output with job ownership check
    query = (
        select(Output)
        .join(Job, Output.job_id == Job.id)
        .where(Output.id == output_id, Job.user_id == user.id)
    )
    result = await db.execute(query)
    output = result.scalar_one_or_none()

    if output is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output not found or access denied.",
        )

    # Delete from R2
    try:
        await storage.delete_object(output.storage_uri)
    except Exception as e:
        # Log but continue - orphaned files can be cleaned up later
        logger.warning(f"Failed to delete output from R2: {output.storage_uri} - {e}")

    # Delete from database
    await db.delete(output)
    await db.flush()
