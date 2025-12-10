"""Output management and publishing endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter()


# === Pydantic Models ===


class OutputResponse(BaseModel):
    """Response model for an output."""

    id: UUID
    job_id: UUID
    output_type: str = Field(description="image | video | model")
    storage_uri: str
    thumbnail_uri: str | None
    metadata: dict[str, Any]
    published_to: list[dict[str, str]]
    created_at: str


class OutputList(BaseModel):
    """Paginated output list."""

    outputs: list[OutputResponse]
    total: int
    skip: int
    limit: int


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
    },
    "instagram": {
        "name": "Instagram",
        "description": "Post to Instagram",
        "icon": "📸",
        "supported_types": ["image", "video"],
    },
    "linkedin": {
        "name": "LinkedIn",
        "description": "Post to LinkedIn",
        "icon": "💼",
        "supported_types": ["image", "video"],
    },
    "discord": {
        "name": "Discord",
        "description": "Post to Discord webhook",
        "icon": "🎮",
        "supported_types": ["image", "video"],
    },
    "webhook": {
        "name": "Custom Webhook",
        "description": "POST to a custom URL",
        "icon": "🔗",
        "supported_types": ["image", "video", "model"],
    },
}


# === Endpoints ===


@router.get("/", response_model=OutputList)
async def list_outputs(
    job_id: UUID | None = None,
    output_type: str | None = None,
    skip: int = 0,
    limit: int = 50,
    # user: User = Depends(get_current_user),
) -> OutputList:
    """
    List generated outputs.

    Browse your materialized creations.
    """
    # TODO: Query database with filters
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Cataloging manifestations...",
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


@router.get("/{output_id}", response_model=OutputResponse)
async def get_output(
    output_id: UUID,
    # user: User = Depends(get_current_user),
) -> OutputResponse:
    """
    Get an output by ID.

    Examine a specific creation.
    """
    # TODO: Query database
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Retrieving manifestation...",
    )


@router.post("/{output_id}/publish", response_model=PublishResponse)
async def publish_output(
    output_id: UUID,
    data: PublishRequest,
    # user: User = Depends(get_current_user),
) -> PublishResponse:
    """
    Publish an output to a channel.

    Broadcast your creation to the world.
    """
    # TODO: Validate channel
    # TODO: Get output from database
    # TODO: Call channel-specific publisher
    # TODO: Update published_to list
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Preparing broadcast...",
    )


@router.delete("/{output_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_output(
    output_id: UUID,
    # user: User = Depends(get_current_user),
) -> None:
    """
    Delete an output.

    Return creation to the void.
    """
    # TODO: Delete from R2
    # TODO: Delete database record
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Dematerializing...",
    )
