"""Output management endpoints with R2 storage integration."""

import logging
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

logger = logging.getLogger(__name__)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth import JanuaUser, get_current_user
from ceq_api.db import get_db
from ceq_api.models import Job, Output
from ceq_api.storage import get_storage, StorageClient

router = APIRouter()


# === Pydantic Models ===


class OutputResponse(BaseModel):
    """Response model for an output."""

    id: UUID
    job_id: UUID
    output_type: str = Field(description="image | video | model")
    storage_uri: str
    public_url: str = Field(description="Direct public URL for the output")
    thumbnail_uri: str | None
    thumbnail_url: str | None = Field(description="Direct public URL for thumbnail")
    metadata: dict[str, Any]
    published_to: list[dict[str, str]]
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
    output_type: str = Field(description="image | video | model")


class UploadUrlResponse(BaseModel):
    """Presigned upload URL response."""

    upload_url: str
    storage_uri: str
    expires_in: int = Field(description="URL expiration in seconds")


class RegisterOutputRequest(BaseModel):
    """Request to register a completed upload as an output."""

    job_id: UUID
    storage_uri: str
    output_type: str = Field(description="image | video | model")
    thumbnail_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


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

OUTPUT_TYPES = {"image", "video", "model"}


# === Helper Functions ===


def _enrich_output_response(
    output: Output,
    storage: StorageClient,
) -> dict[str, Any]:
    """Add public URLs to output response."""
    return {
        "id": output.id,
        "job_id": output.job_id,
        "output_type": output.output_type,
        "storage_uri": output.storage_uri,
        "public_url": storage.get_public_url(output.storage_uri),
        "thumbnail_uri": output.thumbnail_uri,
        "thumbnail_url": (
            storage.get_public_url(output.thumbnail_uri)
            if output.thumbnail_uri
            else None
        ),
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
    job_id: UUID | None = Query(None, description="Filter by job ID"),
    output_type: str | None = Query(None, description="Filter by type: image | video | model"),
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

    # Filter by type
    if output_type:
        if output_type not in OUTPUT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid output_type. Must be one of: {', '.join(OUTPUT_TYPES)}",
            )
        query = query.where(Output.output_type == output_type)

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

    # Validate output type
    if data.output_type not in OUTPUT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid output_type. Must be one of: {', '.join(OUTPUT_TYPES)}",
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
    key = f"outputs/{data.job_id}/{unique_id}_{data.filename}"

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

    # Validate output type
    if data.output_type not in OUTPUT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid output_type. Must be one of: {', '.join(OUTPUT_TYPES)}",
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

    # Create output record
    output = Output(
        job_id=data.job_id,
        user_id=user.id,
        output_type=data.output_type,
        storage_uri=data.storage_uri,
        thumbnail_uri=data.thumbnail_uri,
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

    # Extract filename from storage URI
    filename = output.storage_uri.split("/")[-1]

    download_url = await storage.generate_download_url(
        storage_uri=output.storage_uri,
        expires_in=expires_in,
        filename=filename,
    )

    return DownloadUrlResponse(
        download_url=download_url,
        expires_in=expires_in,
        filename=filename,
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

    # Check if output type is supported by channel
    if output.output_type not in channel_info["supported_types"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{channel_info['name']} does not support {output.output_type} outputs.",
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
                        "output_type": output.output_type,
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
        from datetime import timezone
        publish_record = {
            "channel": data.channel,
            "url": webhook_url,
            "published_at": datetime.now(timezone.utc).isoformat(),
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
        if output.thumbnail_uri:
            await storage.delete_object(output.thumbnail_uri)
    except Exception as e:
        # Log but continue - orphaned files can be cleaned up later
        logger.warning(f"Failed to delete output from R2: {output.storage_uri} - {e}")

    # Delete from database
    await db.delete(output)
    await db.flush()
