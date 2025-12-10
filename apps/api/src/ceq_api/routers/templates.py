"""Template management endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

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
    created_at: str


class TemplateList(BaseModel):
    """Paginated template list."""

    templates: list[TemplateResponse]
    total: int


class ForkTemplateRequest(BaseModel):
    """Request to fork a template into a workflow."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class ForkTemplateResponse(BaseModel):
    """Response after forking a template."""

    workflow_id: UUID
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


@router.get("/", response_model=TemplateList)
async def list_templates(
    category: str | None = None,
    tag: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> TemplateList:
    """
    List available templates.

    Browse the spell library.
    """
    # TODO: Query database with filters
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Cataloging the arcane...",
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
async def get_template(template_id: UUID) -> TemplateResponse:
    """
    Get a template by ID.

    Study a specific spell.
    """
    # TODO: Query database
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Deciphering the glyphs...",
    )


@router.post("/{template_id}/fork", response_model=ForkTemplateResponse)
async def fork_template(
    template_id: UUID,
    data: ForkTemplateRequest,
    # user: User = Depends(get_current_user),
) -> ForkTemplateResponse:
    """
    Fork a template into your own workflow.

    Copy the spell to your grimoire for customization.
    """
    # TODO: Create workflow from template
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Inscribing to grimoire...",
    )
